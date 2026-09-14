from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from rageval.core.settings import Settings
from rageval.generation import GroundedGenerationResponse, RetrievalRouteDecision
from rageval.models import Citation, GroundedAnswer
from rageval.observability import MemoryTraceSink, OperationalTelemetry
from rageval.retrieval.hybrid.models import HybridSearchFilter
from rageval.serving import QueryCacheIdentity, ServingDependencies, StaticHealthCheck, create_app
from rageval.serving.models import EvaluationRunRequest

API_KEY = "phase14-operational-secret"


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "serving_api_key": SecretStr(API_KEY),
        **updates,
    }
    return Settings(**values)


def _response(question: str) -> GroundedGenerationResponse:
    chunk_id = "chk_phase14_api"
    return GroundedGenerationResponse(
        answer=GroundedAnswer(
            question=question,
            answer="Operational fixture answer.",
            citations=[Citation(chunk_id=chunk_id, claim="Operational fixture answer.")],
            cited_chunk_ids=[chunk_id],
            provider="fake",
            model="phase14-fixture",
            input_tokens=4,
            output_tokens=3,
            latency_ms=1.0,
        ),
        retrieval=None,
        context=None,
        route=RetrievalRouteDecision(
            retrieval_required=True,
            router="phase14-fixture",
            reason="fixture",
        ),
        generation_config_fingerprint="3" * 64,
        total_latency_ms=2.0,
    )


class _QueryService:
    async def answer(
        self,
        question: str,
        *,
        filters: HybridSearchFilter | None = None,
        top_k: int | None = None,
    ) -> GroundedGenerationResponse:
        del filters, top_k
        return _response(question)


class _NeverEvaluationExecutor:
    async def run(self, request: EvaluationRunRequest):  # type: ignore[no-untyped-def]
        del request
        raise AssertionError("evaluation should not run in this fixture")


def _app(
    *,
    telemetry: OperationalTelemetry,
    settings: Settings | None = None,
    healthy: bool = True,
):
    dependencies = ServingDependencies(
        query_service=_QueryService(),
        evaluation_executor=_NeverEvaluationExecutor(),
        cache_identity=QueryCacheIdentity(
            index_fingerprint="1" * 64,
            retrieval_config_fingerprint="2" * 64,
            generation_config_fingerprint="3" * 64,
            model_version="fixture-model-v1",
            prompt_version="fixture-prompt-v1",
        ),
        health_checks={
            "qdrant": StaticHealthCheck(healthy=healthy),
            "generation_provider": StaticHealthCheck(),
        },
        telemetry=telemetry,
    )
    return create_app(dependencies=dependencies, settings=settings or _settings())


def test_metrics_trace_security_headers_and_exact_cors() -> None:
    sink = MemoryTraceSink()
    telemetry = OperationalTelemetry(trace_sink=sink)
    app = _app(
        telemetry=telemetry,
        settings=_settings(serving_cors_origins=("https://allowed.example",)),
    )
    headers = {"X-API-Key": API_KEY, "Origin": "https://allowed.example"}

    with TestClient(app) as client:
        response = client.post("/query", headers=headers, json={"question": "safe query"})
        blocked_origin = client.post(
            "/query",
            headers={"X-API-Key": API_KEY, "Origin": "https://blocked.example"},
            json={"question": "another query"},
        )
        metrics = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed.example"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in blocked_origin.headers
    assert metrics.status_code == 200
    assert "rageval_http_requests_total" in metrics.text
    assert 'route="/query"' in metrics.text
    assert "rageval_generation_tokens_total" in metrics.text
    query_records = [record for record in sink.records if record.kind == "query"]
    assert len(query_records) == 2
    assert all(record.query is not None for record in query_records)
    assert all(record.query.query_text is None for record in query_records if record.query is not None)


def test_rate_limit_header_abuse_default_cors_and_degraded_dependency_metrics() -> None:
    telemetry = OperationalTelemetry(trace_sink=MemoryTraceSink())
    app = _app(
        telemetry=telemetry,
        settings=_settings(
            serving_rate_limit_requests=1,
            serving_rate_limit_window_seconds=60.0,
            serving_max_security_header_bytes=128,
        ),
    )
    with TestClient(app) as client:
        first = client.post(
            "/query",
            headers={"X-API-Key": API_KEY, "Origin": "https://not-configured.example"},
            json={"question": "first"},
        )
        limited = client.post(
            "/query",
            headers={"X-API-Key": API_KEY},
            json={"question": "second"},
        )
        abusive = client.post(
            "/query",
            headers={"X-API-Key": "x" * 129},
            json={"question": "header abuse"},
        )

    assert first.status_code == 200
    assert "access-control-allow-origin" not in first.headers
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert abusive.status_code == 431
    assert abusive.json()["code"] == "request_header_too_large"
    assert "x" * 129 not in abusive.text

    degraded_telemetry = OperationalTelemetry(trace_sink=MemoryTraceSink())
    degraded_app = _app(telemetry=degraded_telemetry, healthy=False)
    with TestClient(degraded_app) as client:
        readiness = client.get("/health/ready")
        metrics = client.get("/metrics")
    assert readiness.status_code == 503
    assert 'rageval_dependency_ready{component="qdrant"} 0.0' in metrics.text
    assert 'rageval_http_requests_total{method="GET",route="/health/ready",status_class="5xx"}' in metrics.text


def test_wildcard_cors_is_rejected() -> None:
    with pytest.raises(ValueError, match="wildcard CORS origins"):
        _settings(serving_cors_origins=("*",))
