"""Langfuse-compatible tracing adapters with deterministic redaction semantics."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Mapping
from typing import Any, Literal, Protocol, cast

from rageval.generation.models import GroundedGenerationResponse
from rageval.observability.models import (
    EvaluationTraceDetails,
    OperationalTraceRecord,
    QueryTraceDetails,
    RetrievalTraceItem,
)


class TraceSink(Protocol):
    """Sink for already-sanitized trace records."""

    def record(self, record: OperationalTraceRecord) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class NullTraceSink:
    """Disabled tracing implementation."""

    def record(self, record: OperationalTraceRecord) -> None:
        del record

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class MemoryTraceSink:
    """Deterministic trace sink for unit/integration evidence."""

    def __init__(self) -> None:
        self.records: list[OperationalTraceRecord] = []

    def record(self, record: OperationalTraceRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _LangfuseObservation(Protocol):
    def update(self, **kwargs: object) -> object: ...

    def end(self) -> object: ...


class _LangfuseClient(Protocol):
    def create_trace_id(self, *, seed: str | None = None) -> str: ...

    def start_observation(self, **kwargs: object) -> _LangfuseObservation: ...

    def flush(self) -> object: ...

    def shutdown(self) -> object: ...


class LangfuseTraceSink:
    """Lazy Langfuse v4 adapter over sanitized operational records."""

    def __init__(
        self,
        *,
        public_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        environment: str | None = None,
        client: _LangfuseClient | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return
        module = importlib.import_module("langfuse")
        client_type = cast(Any, vars(module)["Langfuse"])
        self._client = cast(
            _LangfuseClient,
            client_type(
                public_key=public_key,
                secret_key=secret_key,
                base_url=base_url,
                environment=environment,
            ),
        )

    def record(self, record: OperationalTraceRecord) -> None:
        trace_id = self._client.create_trace_id(seed=record.correlation_id)
        payload = record.model_dump(mode="json", exclude_none=True)
        input_payload: Mapping[str, object]
        output_payload: Mapping[str, object]
        if record.kind == "query" and record.query is not None:
            query = record.query.model_dump(mode="json", exclude_none=True)
            input_payload = {
                "query_sha256": query["query_sha256"],
                "query_length": query["query_length"],
                **({"query_text": query["query_text"]} if "query_text" in query else {}),
            }
            output_payload = {
                key: value for key, value in query.items() if key not in input_payload
            }
        else:
            evaluation = (
                record.evaluation.model_dump(mode="json", exclude_none=True)
                if record.evaluation is not None
                else {}
            )
            input_payload = {"job_id": evaluation.get("job_id", record.correlation_id)}
            output_payload = evaluation

        observation = self._client.start_observation(
            name=f"rageval.{record.kind}",
            as_type="span",
            input=dict(input_payload),
            metadata={
                "schema_version": record.schema_version,
                "correlation_id": record.correlation_id,
                "kind": record.kind,
                "rageval_payload": payload,
            },
            trace_context={"trace_id": trace_id},
        )
        observation.update(output=dict(output_payload))
        observation.end()

    def flush(self) -> None:
        self._client.flush()

    def close(self) -> None:
        self._client.shutdown()


def deterministic_trace_id(correlation_id: str) -> str:
    return hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:32]


def build_query_trace(
    *,
    request_id: str,
    question: str,
    response: GroundedGenerationResponse,
    cache_hit: bool,
    api_ms: float,
    include_query_text: bool,
) -> OperationalTraceRecord:
    """Build a safe query trace without retaining raw retrieved document text."""

    retrieval = response.retrieval
    results: list[RetrievalTraceItem] = []
    hop_candidate_ids: tuple[tuple[str, ...], ...] = ()
    retrieval_ms = 0.0
    if retrieval is not None:
        retrieval_ms = retrieval.total_latency_ms
        hop_candidate_ids = tuple(trace.candidate_chunk_ids for trace in retrieval.hop_traces)
        for item in retrieval.final_context:
            metadata = item.retrieval.metadata
            results.append(
                RetrievalTraceItem(
                    chunk_id=item.retrieval.chunk.chunk_id,
                    pre_rerank_rank=_optional_int(item.metadata.get("pre_rerank_rank")),
                    post_rerank_rank=item.rank,
                    dense_rank=_optional_int(metadata.get("dense_rank")),
                    sparse_rank=_optional_int(metadata.get("sparse_rank")),
                    rrf_score=item.retrieval.score,
                    dense_rrf_contribution=_optional_float(
                        metadata.get("dense_rrf_contribution")
                    ),
                    sparse_rrf_contribution=_optional_float(
                        metadata.get("sparse_rrf_contribution")
                    ),
                    rerank_score=item.rerank_score,
                )
            )

    context_ids = response.context.included_chunk_ids if response.context is not None else ()
    cited_ids = tuple(response.answer.cited_chunk_ids)
    citation_valid: bool | None = None
    if response.context is not None:
        citation_valid = set(cited_ids).issubset(set(context_ids))
    total_ms = response.total_latency_ms
    generation_ms = max(total_ms - retrieval_ms, 0.0)
    details = QueryTraceDetails(
        query_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
        query_length=len(question),
        query_text=question if include_query_text else None,
        cache_hit=cache_hit,
        retrieval_required=response.route.retrieval_required,
        route_router=response.route.router,
        hop_candidate_ids=hop_candidate_ids,
        final_results=tuple(results),
        context_chunk_ids=tuple(context_ids),
        context_token_count=response.context.token_count if response.context is not None else 0,
        cited_chunk_ids=cited_ids,
        citations_valid_for_context=citation_valid,
        insufficient_context=response.answer.insufficient_context,
        provider=response.answer.provider,
        model=response.answer.model,
        input_tokens=response.answer.input_tokens,
        output_tokens=response.answer.output_tokens,
        latencies_ms={
            "retrieval": retrieval_ms,
            "generation": generation_ms,
            "pipeline": total_ms,
            "api": api_ms,
        },
    )
    return OperationalTraceRecord(
        trace_id=deterministic_trace_id(request_id),
        kind="query",
        correlation_id=request_id,
        query=details,
    )


def build_evaluation_trace(
    *,
    job_id: str,
    status: str,
    queue_depth: int,
    dataset_fingerprint: str | None = None,
    matrix_fingerprint: str | None = None,
    evidence_label: str | None = None,
    configuration_count: int | None = None,
    duration_ms: float | None = None,
) -> OperationalTraceRecord:
    """Build safe evaluation linkage without serializing evaluation examples."""

    if status not in {"queued", "running", "succeeded", "failed"}:
        raise ValueError(f"unsupported evaluation trace status: {status}")
    typed_status = cast(Literal["queued", "running", "succeeded", "failed"], status)
    details = EvaluationTraceDetails(
        job_id=job_id,
        status=typed_status,
        queue_depth=queue_depth,
        dataset_fingerprint=dataset_fingerprint,
        matrix_fingerprint=matrix_fingerprint,
        evidence_label=evidence_label,
        configuration_count=configuration_count,
        duration_ms=duration_ms,
    )
    return OperationalTraceRecord(
        trace_id=deterministic_trace_id(job_id),
        kind="evaluation",
        correlation_id=job_id,
        evaluation=details,
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
