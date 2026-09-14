"""FastAPI application factory for typed serving and operational hardening."""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from rageval.core.settings import Settings
from rageval.generation.models import GroundedGenerationResponse
from rageval.observability import (
    LangfuseTraceSink,
    OperationalTelemetry,
    SafeAggregateDriftMonitor,
    TraceSink,
)
from rageval.retrieval.hybrid.models import HybridSearchFilter
from rageval.serving.cache import QueryCache, QueryCacheIdentity, build_query_cache_key
from rageval.serving.health import AsyncHealthCheck, HealthRegistry
from rageval.serving.jobs import EvaluationJobExecutor, EvaluationJobManager, EvaluationJobQueueFull
from rageval.serving.models import (
    ComponentHealth,
    EvaluationJobAccepted,
    EvaluationJobStatus,
    EvaluationRunRequest,
    EvaluationSummary,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    RetrievalDiagnostics,
    SafeErrorResponse,
    StageLatency,
    StreamEvent,
)
from rageval.serving.security import FixedWindowRateLimiter

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_SECURITY_HEADER_NAMES = frozenset({"x-api-key", "x-request-id", "origin"})


class QueryService(Protocol):
    async def answer(
        self,
        question: str,
        *,
        filters: HybridSearchFilter | None = None,
        top_k: int | None = None,
    ) -> GroundedGenerationResponse: ...


@dataclass(frozen=True)
class ServingDependencies:
    query_service: QueryService
    evaluation_executor: EvaluationJobExecutor
    cache_identity: QueryCacheIdentity
    cache: QueryCache | None = None
    health_checks: Mapping[str, AsyncHealthCheck] | None = None
    telemetry: OperationalTelemetry | None = None


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Assign request IDs, enforce request limits, and emit metadata-only HTTP telemetry."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_request_bytes: int,
        max_security_header_bytes: int,
        telemetry: OperationalTelemetry,
    ) -> None:
        super().__init__(app)
        self.max_request_bytes = max_request_bytes
        self.max_security_header_bytes = max_security_header_bytes
        self.telemetry = telemetry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else uuid.uuid4().hex
        )
        request.state.request_id = request_id

        for name in _SECURITY_HEADER_NAMES:
            value = request.headers.get(name)
            if value is not None and len(value.encode("utf-8")) > self.max_security_header_bytes:
                response = _safe_json_error(
                    request_id,
                    431,
                    "request_header_too_large",
                    "security-sensitive request header exceeds the configured size limit",
                )
                return self._finish(request, response, started)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = self.max_request_bytes + 1
            if declared_size > self.max_request_bytes:
                response = _safe_json_error(
                    request_id,
                    413,
                    "request_too_large",
                    "request body exceeds the configured size limit",
                )
                return self._finish(request, response, started)
        body = await request.body()
        if len(body) > self.max_request_bytes:
            response = _safe_json_error(
                request_id,
                413,
                "request_too_large",
                "request body exceeds the configured size limit",
            )
            return self._finish(request, response, started)

        response = await call_next(request)
        return self._finish(request, response, started)

    def _finish(self, request: Request, response: Response, started: float) -> Response:
        request_id = _request_id(request)
        duration_ms = (time.perf_counter() - started) * 1000.0
        response.headers["x-request-id"] = request_id
        _apply_security_headers(response)
        self.telemetry.record_http(
            route=_route_template(request),
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        logger.info(
            "http request",
            extra={
                "context": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response


def create_app(
    *,
    dependencies: ServingDependencies,
    settings: Settings | None = None,
) -> FastAPI:
    """Build the typed API around injected production/test services."""

    config = settings or Settings()
    if config.serving_api_key is None:
        raise ValueError("RAGEVAL_SERVING_API_KEY must be configured before serving HTTP requests")
    expected_api_key = config.serving_api_key.get_secret_value()
    telemetry = dependencies.telemetry or _build_telemetry(config)
    query_semaphore = asyncio.Semaphore(config.serving_query_concurrency)
    rate_limiter = FixedWindowRateLimiter(
        max_requests=config.serving_rate_limit_requests,
        window_seconds=config.serving_rate_limit_window_seconds,
    )
    job_manager = EvaluationJobManager(
        executor=dependencies.evaluation_executor,
        max_concurrency=config.serving_eval_job_concurrency,
        max_queue_size=config.serving_eval_queue_size,
        telemetry=telemetry,
    )
    checks = dict(dependencies.health_checks or {})
    if dependencies.cache is not None and "redis" not in checks:
        checks["redis"] = dependencies.cache.ping
    health_registry = HealthRegistry(checks)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await job_manager.start()
        try:
            yield
        finally:
            await job_manager.stop()
            if dependencies.cache is not None:
                await dependencies.cache.aclose()
            try:
                telemetry.flush()
                telemetry.close()
            except Exception as exc:
                logger.error("telemetry shutdown failed (%s)", type(exc).__name__)

    app = FastAPI(
        title="RAG-Eval API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        RequestGuardMiddleware,
        max_request_bytes=config.serving_max_request_bytes,
        max_security_header_bytes=config.serving_max_security_header_bytes,
        telemetry=telemetry,
    )
    if config.serving_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.serving_cors_origins),
            allow_credentials=config.serving_cors_allow_credentials,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )

    async def require_api_key(
        api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        if api_key is None:
            raise HTTPException(
                status_code=401,
                detail="API key is required",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        if not hmac.compare_digest(api_key.encode("utf-8"), expected_api_key.encode("utf-8")):
            raise HTTPException(status_code=403, detail="API key is invalid")
        allowed, retry_after = await rate_limiter.allow(api_key)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="request rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

    async def execute_query(payload: QueryRequest, request_id: str) -> QueryResponse:
        started = time.perf_counter()
        cache_hit = False
        cache_outcome = "bypass"
        result: GroundedGenerationResponse | None = None
        cache_key = build_query_cache_key(payload, dependencies.cache_identity)
        if payload.options.use_cache and dependencies.cache is not None:
            cache_outcome = "miss"
            cached = await dependencies.cache.get(cache_key)
            if cached is not None:
                result = GroundedGenerationResponse.model_validate_json(cached)
                cache_hit = True
                cache_outcome = "hit"

        if result is None:
            try:
                async with asyncio.timeout(config.serving_request_timeout_seconds):
                    async with query_semaphore:
                        result = await dependencies.query_service.answer(
                            payload.question,
                            filters=payload.retrieval_filters(),
                            top_k=payload.top_k,
                        )
            except TimeoutError as exc:
                telemetry.record_provider_failure(operation="query", provider="other")
                raise HTTPException(status_code=504, detail="query timed out") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid query options") from exc
            except Exception:
                telemetry.record_provider_failure(operation="query", provider="other")
                raise
            if payload.options.use_cache and dependencies.cache is not None:
                await dependencies.cache.set(
                    cache_key,
                    result.model_dump_json(),
                    ttl_seconds=config.serving_cache_ttl_seconds,
                )

        api_ms = (time.perf_counter() - started) * 1000.0
        _record_query_telemetry(
            telemetry,
            request_id=request_id,
            question=payload.question,
            response=result,
            cache_hit=cache_hit,
            cache_outcome=cache_outcome,
            api_ms=api_ms,
        )
        return _to_query_response(
            result,
            request_id=request_id,
            cache_hit=cache_hit,
            api_ms=api_ms,
            expose_diagnostics=(
                config.serving_expose_retrieval_diagnostics
                and payload.options.include_retrieval_diagnostics
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return _safe_json_error(
            _request_id(request),
            422,
            "validation_error",
            "request validation failed",
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled serving error (%s)",
            type(exc).__name__,
            extra={"context": {"request_id": _request_id(request), "path": request.url.path}},
        )
        return _safe_json_error(
            _request_id(request),
            500,
            "internal_error",
            "internal server error",
        )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def health_live() -> HealthResponse:
        return HealthResponse(
            status=ComponentHealth.OK,
            components={"process": ComponentHealth.OK},
        )

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def health_ready() -> HealthResponse | JSONResponse:
        report = await health_registry.readiness()
        for name, status in report.components.items():
            telemetry.record_dependency(name, healthy=status is ComponentHealth.OK)
        if report.status is ComponentHealth.DEGRADED:
            return JSONResponse(status_code=503, content=report.model_dump(mode="json"))
        return report

    @app.get("/metrics", include_in_schema=False, tags=["observability"])
    async def metrics() -> Response:
        return Response(
            content=telemetry.metrics.render(),
            headers={"Content-Type": telemetry.metrics.content_type},
        )

    @app.post(
        "/query",
        response_model=QueryResponse,
        dependencies=[Depends(require_api_key)],
        tags=["query"],
    )
    async def query(payload: QueryRequest, request: Request) -> QueryResponse | StreamingResponse:
        request_id = _request_id(request)
        if payload.options.stream:
            return StreamingResponse(
                _stream_query(
                    request=request,
                    payload=payload,
                    request_id=request_id,
                    execute=execute_query,
                    chunk_chars=config.serving_stream_chunk_chars,
                ),
                media_type="application/x-ndjson",
                headers={"x-request-id": request_id},
            )
        return await execute_query(payload, request_id)

    @app.post(
        "/eval/run",
        response_model=EvaluationJobAccepted,
        status_code=202,
        dependencies=[Depends(require_api_key)],
        tags=["evaluation"],
    )
    async def start_evaluation(payload: EvaluationRunRequest) -> EvaluationJobAccepted:
        try:
            return await job_manager.submit(payload)
        except EvaluationJobQueueFull as exc:
            raise HTTPException(status_code=429, detail="evaluation queue is full") from exc

    @app.get(
        "/eval/jobs/{job_id}",
        response_model=EvaluationJobStatus,
        dependencies=[Depends(require_api_key)],
        tags=["evaluation"],
    )
    async def evaluation_status(job_id: str) -> EvaluationJobStatus:
        status = await job_manager.status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="evaluation job not found")
        return status

    @app.get(
        "/eval/latest",
        response_model=EvaluationSummary,
        dependencies=[Depends(require_api_key)],
        tags=["evaluation"],
    )
    async def latest_evaluation() -> EvaluationSummary:
        summary = await job_manager.latest()
        if summary is None:
            raise HTTPException(status_code=404, detail="no completed evaluation is available")
        return summary

    return app


def _build_telemetry(config: Settings) -> OperationalTelemetry:
    trace_sink: TraceSink | None = None
    if config.tracing_provider == "langfuse":
        if config.langfuse_public_key is None or config.langfuse_secret_key is None:
            raise ValueError("Langfuse tracing requires configured public and secret keys")
        trace_sink = LangfuseTraceSink(
            public_key=config.langfuse_public_key.get_secret_value(),
            secret_key=config.langfuse_secret_key.get_secret_value(),
            base_url=config.langfuse_host,
            environment=config.app_env,
        )
    return OperationalTelemetry(
        trace_sink=trace_sink,
        drift_monitor=SafeAggregateDriftMonitor(
            min_samples=config.drift_min_samples,
            relative_shift_threshold=config.drift_relative_shift_threshold,
        ),
        include_query_text=config.observability_include_query_text,
    )


def _record_query_telemetry(
    telemetry: OperationalTelemetry,
    *,
    request_id: str,
    question: str,
    response: GroundedGenerationResponse,
    cache_hit: bool,
    cache_outcome: str,
    api_ms: float,
) -> None:
    try:
        telemetry.record_query(
            request_id=request_id,
            question=question,
            response=response,
            cache_hit=cache_hit,
            cache_outcome=cache_outcome,
            api_ms=api_ms,
        )
    except Exception as exc:
        logger.error(
            "query telemetry failed (%s)",
            type(exc).__name__,
            extra={"context": {"request_id": request_id}},
        )


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else uuid.uuid4().hex


def _apply_security_headers(response: Response) -> None:
    response.headers.setdefault("x-content-type-options", "nosniff")
    response.headers.setdefault("x-frame-options", "DENY")
    response.headers.setdefault("referrer-policy", "no-referrer")
    response.headers.setdefault("cache-control", "no-store")


def _safe_json_error(
    request_id: str,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    payload = SafeErrorResponse(request_id=request_id, code=code, message=message)
    response = JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers={"x-request-id": request_id},
    )
    _apply_security_headers(response)
    return response


def _to_query_response(
    result: GroundedGenerationResponse,
    *,
    request_id: str,
    cache_hit: bool,
    api_ms: float,
    expose_diagnostics: bool,
) -> QueryResponse:
    retrieval_ms = result.retrieval.total_latency_ms if result.retrieval is not None else 0.0
    total_pipeline_ms = result.total_latency_ms
    generation_ms = max(total_pipeline_ms - retrieval_ms, 0.0)
    retrieval = None
    if expose_diagnostics and result.retrieval is not None:
        retrieval = RetrievalDiagnostics(
            service_config_fingerprint=result.retrieval.service_config_fingerprint,
            rerank_config_fingerprint=result.retrieval.rerank_config_fingerprint,
            final_chunk_ids=tuple(
                item.retrieval.chunk.chunk_id for item in result.retrieval.final_context
            ),
            hop_count=len(result.retrieval.hop_traces),
            multi_hop_triggered=result.retrieval.multi_hop.triggered,
        )
    answer = result.answer
    return QueryResponse(
        request_id=request_id,
        answer=answer.answer,
        citations=tuple(answer.citations),
        cited_chunk_ids=tuple(answer.cited_chunk_ids),
        insufficient_context=answer.insufficient_context,
        refusal_reason=answer.refusal_reason,
        provider=answer.provider,
        model=answer.model,
        cache_hit=cache_hit,
        latency=StageLatency(
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            total_pipeline_ms=total_pipeline_ms,
            api_ms=api_ms,
        ),
        retrieval=retrieval,
    )


async def _stream_query(
    *,
    request: Request,
    payload: QueryRequest,
    request_id: str,
    execute: Callable[[QueryRequest, str], Awaitable[QueryResponse]],
    chunk_chars: int,
) -> AsyncIterator[bytes]:
    async def run() -> QueryResponse:
        return await execute(payload, request_id)

    task = asyncio.create_task(run(), name=f"rageval-stream-query-{request_id}")
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return
            await asyncio.sleep(0.01)
        response = await task
        for offset in range(0, len(response.answer), chunk_chars):
            if await request.is_disconnected():
                return
            event = StreamEvent(
                event="answer_delta",
                data={"text": response.answer[offset : offset + chunk_chars]},
            )
            yield (event.model_dump_json() + "\n").encode("utf-8")
        final = StreamEvent(event="final", data=response.model_dump(mode="json"))
        yield (final.model_dump_json() + "\n").encode("utf-8")
    except HTTPException as exc:
        error = StreamEvent(
            event="error",
            data={"code": f"http_{exc.status_code}", "message": "streaming query failed"},
        )
        yield (error.model_dump_json() + "\n").encode("utf-8")
    except Exception as exc:
        logger.error(
            "streaming query failed (%s)",
            type(exc).__name__,
            extra={"context": {"request_id": request_id}},
        )
        error = StreamEvent(
            event="error",
            data={"code": "internal_error", "message": "streaming query failed"},
        )
        yield (error.model_dump_json() + "\n").encode("utf-8")
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
