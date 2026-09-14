"""Typed operational trace contracts for safe RAG-Eval observability."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from rageval.models.contracts import ContractModel


class RetrievalTraceItem(ContractModel):
    """Safe rank/fusion/rerank diagnostics for one final context item."""

    chunk_id: str = Field(min_length=8)
    pre_rerank_rank: int | None = Field(default=None, ge=1)
    post_rerank_rank: int = Field(ge=1)
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_rank: int | None = Field(default=None, ge=1)
    rrf_score: float | None = None
    dense_rrf_contribution: float | None = None
    sparse_rrf_contribution: float | None = None
    rerank_score: float


class QueryTraceDetails(ContractModel):
    """Query trace details that avoid raw document content by construction."""

    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_length: int = Field(ge=0)
    query_text: str | None = None
    cache_hit: bool
    retrieval_required: bool
    route_router: str = Field(min_length=1)
    hop_candidate_ids: tuple[tuple[str, ...], ...] = ()
    final_results: tuple[RetrievalTraceItem, ...] = ()
    context_chunk_ids: tuple[str, ...] = ()
    context_token_count: int = Field(default=0, ge=0)
    cited_chunk_ids: tuple[str, ...] = ()
    citations_valid_for_context: bool | None = None
    insufficient_context: bool
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latencies_ms: dict[str, float] = Field(default_factory=dict)


class EvaluationTraceDetails(ContractModel):
    """Evaluation-job linkage without embedding full examples or answers."""

    job_id: str = Field(min_length=8)
    status: Literal["queued", "running", "succeeded", "failed"]
    queue_depth: int = Field(ge=0)
    dataset_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    matrix_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_label: str | None = None
    configuration_count: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0.0)


class OperationalTraceRecord(ContractModel):
    """One Langfuse-compatible operational record keyed by safe correlation identity."""

    schema_version: str = "1.0"
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["query", "evaluation"]
    correlation_id: str = Field(min_length=8)
    query: QueryTraceDetails | None = None
    evaluation: EvaluationTraceDetails | None = None
