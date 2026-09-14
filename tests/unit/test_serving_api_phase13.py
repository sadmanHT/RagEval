from __future__ import annotations

import asyncio
import json
import time

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from rageval.core.settings import Settings
from rageval.evaluation import (
    AblationConfiguration,
    ChunkingStrategy,
    ComparativeEvaluationReport,
    ConfigurationRun,
    EvaluationRun,
    HallucinationSummary,
    MetricSlice,
    RetrievalPipeline,
)
from rageval.generation import GroundedGenerationResponse, RetrievalRouteDecision
from rageval.models import Citation, Domain, GroundedAnswer
from rageval.retrieval.hybrid.models import HybridSearchFilter
from rageval.serving import (
    MemoryQueryCache,
    QueryCacheIdentity,
    ServingDependencies,
    StaticHealthCheck,
    create_app,
)
from rageval.serving.models import EvaluationRunRequest

API_KEY = "phase13-test-secret-key"


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "serving_api_key": SecretStr(API_KEY),
        "serving_expose_retrieval_diagnostics": True,
        **updates,
    }
    return Settings(**values)


def _identity(index: str = "1") -> QueryCacheIdentity:
    return QueryCacheIdentity(
        index_fingerprint=index * 64,
        retrieval_config_fingerprint="2" * 64,
        generation_config_fingerprint="3" * 64,
        model_version="fixture-model-v1",
        prompt_version="fixture-prompt-v1",
    )


def _grounded_response(question: str) -> GroundedGenerationResponse:
    chunk_id = "chk_phase13_fixture"
    return GroundedGenerationResponse(
        answer=GroundedAnswer(
            question=question,
            answer="The supported fixture answer is 42.",
            citations=[Citation(chunk_id=chunk_id, claim="The supported fixture answer is 42.")],
            cited_chunk_ids=[chunk_id],
            provider="phase13-fixture",
            model="fixture-v1",
            latency_ms=1.0,
        ),
        retrieval=None,
        context=None,
        route=RetrievalRouteDecision(
            retrieval_required=True,
            router="phase13-fixture",
            reason="fixture route",
        ),
        generation_config_fingerprint="3" * 64,
        total_latency_ms=3.0,
    )


class RecordingQueryService:
    def __init__(self, *, delay: float = 0.0) -> None:
        self.calls = 0
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.last_top_k: int | None = None
        self.last_filters: HybridSearchFilter | None = None

    async def answer(
        self,
        question: str,
        *,
        filters: HybridSearchFilter | None = None,
        top_k: int | None = None,
    ) -> GroundedGenerationResponse:
        self.calls += 1
        self.last_top_k = top_k
        self.last_filters = filters
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return _grounded_response(question)
        finally:
            self.active -= 1


class SensitiveFailureQueryService(RecordingQueryService):
    async def answer(
        self,
        question: str,
        *,
        filters: HybridSearchFilter | None = None,
        top_k: int | None = None,
    ) -> GroundedGenerationResponse:
        del question, filters, top_k
        raise RuntimeError("provider failed with token provider-secret-must-not-leak")


class FixtureEvaluationExecutor:
    async def run(self, request: EvaluationRunRequest) -> ComparativeEvaluationReport:
        del request
        evaluation = EvaluationRun(
            dataset_fingerprint="a" * 64,
            config_fingerprint="b" * 64,
            run_fingerprint="c" * 64,
            judge_provider="fixture",
            judge_model="fixture-v1",
            records=(),
            aggregates=(),
            hallucination=HallucinationSummary(
                threshold=0.8,
                flagged_count=0,
                total_count=0,
                rate=0.0,
            ),
        )
        run = ConfigurationRun(
            run_id="d" * 64,
            config=AblationConfiguration(
                config_id="phase13-fixture",
                retrieval_pipeline=RetrievalPipeline.HYBRID_RERANK,
                chunking_strategy=ChunkingStrategy.FIXED_512,
            ),
            dataset_fingerprint="a" * 64,
            config_fingerprint="e" * 64,
            evaluation=evaluation,
            metric_slices=(MetricSlice(metric="faithfulness", count=3, mean_score=1.0),),
        )
        return ComparativeEvaluationReport(
            dataset_fingerprint="a" * 64,
            matrix_fingerprint="f" * 64,
            runs=(run,),
            evidence_label="phase13-fixture-mechanics-only",
        )


def _app(
    service: RecordingQueryService | None = None,
    *,
    cache: MemoryQueryCache | None = None,
    settings: Settings | None = None,
    healthy: bool = True,
):
    query_service = service or RecordingQueryService()
    dependencies = ServingDependencies(
        query_service=query_service,
        evaluation_executor=FixtureEvaluationExecutor(),
        cache_identity=_identity(),
        cache=cache,
        health_checks={
            "qdrant": StaticHealthCheck(healthy=healthy),
            "generation_provider": StaticHealthCheck(),
        },
    )
    return create_app(dependencies=dependencies, settings=settings or _settings())


def test_openapi_auth_and_query_contract() -> None:
    service = RecordingQueryService()
    app = _app(service)
    schema = app.openapi()
    assert {"/query", "/eval/run", "/eval/jobs/{job_id}", "/eval/latest"} <= set(schema["paths"])

    with TestClient(app) as client:
        assert client.post("/query", json={"question": "What?"}).status_code == 401
        invalid = client.post(
            "/query",
            headers={"X-API-Key": "wrong-secret"},
            json={"question": "What?"},
        )
        assert invalid.status_code == 403
        response = client.post(
            "/query",
            headers={"X-API-Key": API_KEY, "X-Request-ID": "request-1234"},
            json={"question": "What?", "domain": "legal", "top_k": 3},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "request-1234"
    assert payload["cited_chunk_ids"] == ["chk_phase13_fixture"]
    assert response.headers["x-request-id"] == "request-1234"
    assert service.last_top_k == 3
    assert service.last_filters is not None
    assert service.last_filters.domain is Domain.LEGAL


def test_cache_hit_and_stream_final_event_preserve_citations() -> None:
    service = RecordingQueryService()
    cache = MemoryQueryCache()
    app = _app(service, cache=cache)
    headers = {"X-API-Key": API_KEY}

    with TestClient(app) as client:
        first = client.post("/query", headers=headers, json={"question": "cached question"})
        second = client.post("/query", headers=headers, json={"question": "cached question"})
        streamed = client.post(
            "/query",
            headers=headers,
            json={
                "question": "streamed question",
                "options": {"stream": True, "use_cache": False},
            },
        )

    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert service.calls == 2
    events = [json.loads(line) for line in streamed.text.splitlines()]
    final = [event for event in events if event["event"] == "final"][-1]
    assert final["data"]["cited_chunk_ids"] == ["chk_phase13_fixture"]


def test_evaluation_job_lifecycle_and_readiness_degradation() -> None:
    headers = {"X-API-Key": API_KEY}
    with TestClient(_app()) as client:
        created = client.post("/eval/run", headers=headers, json={})
        assert created.status_code == 202
        job_id = created.json()["job_id"]
        for _ in range(50):
            status = client.get(f"/eval/jobs/{job_id}", headers=headers)
            if status.json()["status"] == "succeeded":
                break
            time.sleep(0.01)
        assert status.json()["status"] == "succeeded"
        latest = client.get("/eval/latest", headers=headers)
        assert latest.status_code == 200
        assert latest.json()["job_id"] == job_id

    with TestClient(_app(healthy=False)) as client:
        readiness = client.get("/health/ready")
    assert readiness.status_code == 503
    assert readiness.json()["components"]["qdrant"] == "degraded"


async def test_query_concurrency_is_bounded() -> None:
    service = RecordingQueryService(delay=0.03)
    app = _app(service, settings=_settings(serving_query_concurrency=2))
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                *(
                    client.post(
                        "/query",
                        headers={"X-API-Key": API_KEY},
                        json={"question": f"question {index}", "options": {"use_cache": False}},
                    )
                    for index in range(6)
                )
            )
    assert all(response.status_code == 200 for response in responses)
    assert service.max_active <= 2


def test_request_size_and_secret_regression(caplog) -> None:
    app = _app(settings=_settings(serving_max_request_bytes=1024))
    oversized = "x" * 2000
    with TestClient(app) as client:
        response = client.post(
            "/query",
            headers={"X-API-Key": API_KEY},
            json={"question": oversized},
        )
        invalid = client.post(
            "/query",
            headers={"X-API-Key": "do-not-leak-this-secret"},
            json={"question": "safe"},
        )
    assert response.status_code == 413
    assert invalid.status_code == 403
    assert "do-not-leak-this-secret" not in invalid.text
    assert "do-not-leak-this-secret" not in caplog.text


def test_unhandled_errors_do_not_log_secret_bearing_exception_text(caplog) -> None:
    app = _app(SensitiveFailureQueryService())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/query",
            headers={"X-API-Key": API_KEY},
            json={"question": "trigger provider failure", "options": {"use_cache": False}},
        )

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "provider-secret-must-not-leak" not in response.text
    assert "provider-secret-must-not-leak" not in caplog.text
    assert "RuntimeError" in caplog.text
