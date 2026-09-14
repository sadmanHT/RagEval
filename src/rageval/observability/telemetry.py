"""Composition layer connecting traces, metrics, and safe aggregate drift hooks."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from rageval.generation.models import GroundedGenerationResponse
from rageval.observability.drift import SafeAggregateDriftMonitor
from rageval.observability.metrics import PrometheusMetrics
from rageval.observability.models import OperationalTraceRecord
from rageval.observability.tracing import (
    NullTraceSink,
    TraceSink,
    build_evaluation_trace,
    build_query_trace,
)

logger = logging.getLogger(__name__)


class OperationalTelemetry:
    """Operational instrumentation with deterministic local defaults."""

    def __init__(
        self,
        *,
        metrics: PrometheusMetrics | None = None,
        trace_sink: TraceSink | None = None,
        drift_monitor: SafeAggregateDriftMonitor | None = None,
        include_query_text: bool = False,
    ) -> None:
        self.metrics = metrics or PrometheusMetrics()
        self.trace_sink = trace_sink or NullTraceSink()
        self.drift_monitor = drift_monitor or SafeAggregateDriftMonitor()
        self.include_query_text = include_query_text

    def record_http(
        self,
        *,
        route: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        self.metrics.observe_http(
            route=route,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
        )

    def record_query(
        self,
        *,
        request_id: str,
        question: str,
        response: GroundedGenerationResponse,
        cache_hit: bool,
        cache_outcome: str,
        api_ms: float,
    ) -> None:
        self.drift_monitor.observe_query(question)
        self.metrics.query_length.observe(len(question))
        trace = build_query_trace(
            request_id=request_id,
            question=question,
            response=response,
            cache_hit=cache_hit,
            api_ms=api_ms,
            include_query_text=self.include_query_text,
        )
        if trace.query is None:
            raise RuntimeError("query trace construction returned no query details")
        for stage, latency_ms in trace.query.latencies_ms.items():
            self.metrics.observe_stage(stage, latency_ms)
        self.metrics.observe_cache(cache_outcome)
        self.metrics.observe_tokens(
            provider=response.answer.provider,
            input_tokens=response.answer.input_tokens,
            output_tokens=response.answer.output_tokens,
        )
        estimated_cost = _estimated_cost(response.answer.metadata)
        self.metrics.observe_estimated_cost(
            provider=response.answer.provider,
            cost=estimated_cost,
        )
        self._record_trace(trace)

    def record_embedding(self, vector: Sequence[float], *, baseline: bool = False) -> None:
        """Public hook for embedding adapters; stores only vector norms."""
        self.drift_monitor.observe_embedding(vector, baseline=baseline)

    def record_provider_failure(self, *, operation: str, provider: str) -> None:
        self.metrics.observe_provider_failure(operation=operation, provider=provider)

    def record_dependency(self, component: str, *, healthy: bool) -> None:
        self.metrics.observe_dependency(component, healthy=healthy)

    def record_evaluation_job(
        self,
        *,
        job_id: str,
        status: str,
        queue_depth: int,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        dataset_fingerprint: str | None = None,
        matrix_fingerprint: str | None = None,
        evidence_label: str | None = None,
        configuration_count: int | None = None,
    ) -> None:
        duration_ms: float | None = None
        if started_at is not None and completed_at is not None:
            duration_ms = max((completed_at - started_at).total_seconds() * 1000.0, 0.0)
        self.metrics.observe_evaluation_job(
            status=status,
            queue_depth=queue_depth,
            duration_ms=duration_ms,
        )
        if status == "failed":
            self.metrics.observe_provider_failure(operation="evaluation", provider="other")
        self._record_trace(
            build_evaluation_trace(
                job_id=job_id,
                status=status,
                queue_depth=queue_depth,
                dataset_fingerprint=dataset_fingerprint,
                matrix_fingerprint=matrix_fingerprint,
                evidence_label=evidence_label,
                configuration_count=configuration_count,
                duration_ms=duration_ms,
            )
        )

    def _record_trace(self, record: OperationalTraceRecord) -> None:
        try:
            self.trace_sink.record(record)
        except Exception as exc:
            self.metrics.observe_provider_failure(operation="tracing", provider="other")
            logger.error("trace export failed (%s)", type(exc).__name__)

    def flush(self) -> None:
        self.trace_sink.flush()

    def close(self) -> None:
        self.trace_sink.close()


def _estimated_cost(metadata: dict[str, object]) -> float | None:
    value = metadata.get("estimated_cost")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
