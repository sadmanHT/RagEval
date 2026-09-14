"""Low-cardinality Prometheus metrics for serving and evaluation operations."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_ALLOWED_ROUTES = {
    "/query",
    "/eval/run",
    "/eval/jobs/{job_id}",
    "/eval/latest",
    "/health/live",
    "/health/ready",
    "/metrics",
}
_ALLOWED_PROVIDERS = {
    "openai",
    "cohere",
    "anthropic",
    "local",
    "fake",
    "deterministic-fake",
}


class PrometheusMetrics:
    """Per-application registry to avoid global test/process metric collisions."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)
        self.http_requests = Counter(
            "rageval_http_requests_total",
            "HTTP requests by bounded route/method/status class.",
            ("route", "method", "status_class"),
            registry=self.registry,
        )
        self.http_errors = Counter(
            "rageval_http_errors_total",
            "HTTP error responses by bounded route/status class.",
            ("route", "status_class"),
            registry=self.registry,
        )
        self.http_latency = Histogram(
            "rageval_http_request_duration_seconds",
            "HTTP request latency histogram for p50/p95/p99 calculation.",
            ("route", "method"),
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.stage_latency = Histogram(
            "rageval_pipeline_stage_duration_seconds",
            "Retrieval/generation/pipeline/API latency by fixed stage.",
            ("stage",),
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.cache_requests = Counter(
            "rageval_cache_requests_total",
            "Query-cache outcomes.",
            ("outcome",),
            registry=self.registry,
        )
        self.provider_failures = Counter(
            "rageval_provider_failures_total",
            "Provider or pipeline failures by bounded operation/provider label.",
            ("operation", "provider"),
            registry=self.registry,
        )
        self.tokens = Counter(
            "rageval_generation_tokens_total",
            "Generation tokens where provider usage is available.",
            ("direction", "provider"),
            registry=self.registry,
        )
        self.estimated_cost = Counter(
            "rageval_generation_estimated_cost_total",
            "Estimated generation cost when explicitly supplied by an adapter.",
            ("provider",),
            registry=self.registry,
        )
        self.evaluation_jobs = Counter(
            "rageval_evaluation_jobs_total",
            "Evaluation-job lifecycle transitions.",
            ("status",),
            registry=self.registry,
        )
        self.evaluation_duration = Histogram(
            "rageval_evaluation_job_duration_seconds",
            "Completed evaluation-job duration.",
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.evaluation_queue_depth = Gauge(
            "rageval_evaluation_queue_depth",
            "Current in-process evaluation queue depth.",
            registry=self.registry,
        )
        self.dependency_ready = Gauge(
            "rageval_dependency_ready",
            "Dependency readiness (1=ready, 0=degraded).",
            ("component",),
            registry=self.registry,
        )
        self.query_length = Histogram(
            "rageval_query_length_characters",
            "Safe query-length distribution without raw query contents.",
            buckets=(16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192),
            registry=self.registry,
        )

    def observe_http(
        self,
        *,
        route: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        bounded_route = bounded_route_label(route)
        status_class = f"{status_code // 100}xx" if 100 <= status_code <= 599 else "other"
        method_label = method.upper() if method.upper() in {"GET", "POST"} else "OTHER"
        self.http_requests.labels(bounded_route, method_label, status_class).inc()
        self.http_latency.labels(bounded_route, method_label).observe(
            max(duration_ms, 0.0) / 1000.0
        )
        if status_code >= 400:
            self.http_errors.labels(bounded_route, status_class).inc()

    def observe_stage(self, stage: str, duration_ms: float) -> None:
        if stage not in {"retrieval", "generation", "pipeline", "api"}:
            raise ValueError(f"unsupported stage metric: {stage}")
        self.stage_latency.labels(stage).observe(max(duration_ms, 0.0) / 1000.0)

    def observe_cache(self, outcome: str) -> None:
        if outcome not in {"hit", "miss", "bypass"}:
            raise ValueError(f"unsupported cache outcome: {outcome}")
        self.cache_requests.labels(outcome).inc()

    def observe_provider_failure(self, *, operation: str, provider: str) -> None:
        operation_label = operation if operation in {"query", "evaluation", "tracing"} else "other"
        provider_label = provider if provider in _ALLOWED_PROVIDERS else "other"
        self.provider_failures.labels(operation_label, provider_label).inc()

    def observe_tokens(self, *, provider: str, input_tokens: int, output_tokens: int) -> None:
        provider_label = provider if provider in _ALLOWED_PROVIDERS else "other"
        self.tokens.labels("input", provider_label).inc(max(input_tokens, 0))
        self.tokens.labels("output", provider_label).inc(max(output_tokens, 0))

    def observe_estimated_cost(self, *, provider: str, cost: float | None) -> None:
        if cost is None or cost < 0:
            return
        provider_label = provider if provider in _ALLOWED_PROVIDERS else "other"
        self.estimated_cost.labels(provider_label).inc(cost)

    def observe_evaluation_job(
        self,
        *,
        status: str,
        queue_depth: int,
        duration_ms: float | None = None,
    ) -> None:
        if status not in {"queued", "running", "succeeded", "failed"}:
            raise ValueError(f"unsupported evaluation status: {status}")
        self.evaluation_jobs.labels(status).inc()
        self.evaluation_queue_depth.set(max(queue_depth, 0))
        if duration_ms is not None:
            self.evaluation_duration.observe(max(duration_ms, 0.0) / 1000.0)

    def observe_dependency(self, component: str, *, healthy: bool) -> None:
        component_label = (
            component
            if component in {"qdrant", "redis", "generation_provider"}
            else "other"
        )
        self.dependency_ready.labels(component_label).set(1.0 if healthy else 0.0)

    def render(self) -> bytes:
        return generate_latest(self.registry)

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST


def bounded_route_label(route: str) -> str:
    return route if route in _ALLOWED_ROUTES else "other"
