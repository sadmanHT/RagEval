"""Versioned HTTP boundary contracts for Phase 13 serving."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from rageval.models import Citation, Domain
from rageval.models.contracts import ContractModel
from rageval.retrieval.hybrid.models import HybridSearchFilter


class QueryFilters(ContractModel):
    """HTTP-safe retrieval filters mapped onto the canonical hybrid filter contract."""

    document_id: str | None = Field(default=None, min_length=8, max_length=256)
    date_from: date | None = None
    date_to: date | None = None
    chunking_config_fingerprint: str | None = Field(default=None, min_length=16, max_length=128)

    @model_validator(mode="after")
    def validate_dates(self) -> QueryFilters:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be <= date_to")
        return self


class QueryOptions(ContractModel):
    """Request-scoped serving options that do not mutate retrieval configuration."""

    use_cache: bool = True
    include_retrieval_diagnostics: bool = False
    stream: bool = False


class QueryRequest(ContractModel):
    schema_version: str = "1.0"
    question: str = Field(min_length=1, max_length=10_000)
    domain: Domain | None = None
    filters: QueryFilters = Field(default_factory=QueryFilters)
    top_k: int | None = Field(default=None, ge=1, le=100)
    options: QueryOptions = Field(default_factory=QueryOptions)

    @model_validator(mode="after")
    def validate_question(self) -> QueryRequest:
        if not self.question.strip():
            raise ValueError("question must not be blank")
        return self

    def retrieval_filters(self) -> HybridSearchFilter:
        return HybridSearchFilter(
            domain=self.domain,
            document_id=self.filters.document_id,
            date_from=self.filters.date_from,
            date_to=self.filters.date_to,
            chunking_config_fingerprint=self.filters.chunking_config_fingerprint,
        )


class StageLatency(ContractModel):
    retrieval_ms: float = Field(ge=0.0)
    generation_ms: float = Field(ge=0.0)
    total_pipeline_ms: float = Field(ge=0.0)
    api_ms: float = Field(ge=0.0)


class RetrievalDiagnostics(ContractModel):
    service_config_fingerprint: str = Field(min_length=16)
    rerank_config_fingerprint: str = Field(min_length=16)
    final_chunk_ids: tuple[str, ...] = ()
    hop_count: int = Field(ge=0)
    multi_hop_triggered: bool


class QueryResponse(ContractModel):
    schema_version: str = "1.0"
    request_id: str = Field(min_length=8, max_length=128)
    answer: str
    citations: tuple[Citation, ...] = ()
    cited_chunk_ids: tuple[str, ...] = ()
    insufficient_context: bool = False
    refusal_reason: str | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    cache_hit: bool = False
    latency: StageLatency
    retrieval: RetrievalDiagnostics | None = None


class StreamEvent(ContractModel):
    schema_version: str = "1.0"
    event: Literal["answer_delta", "final", "error"]
    data: dict[str, object] = Field(default_factory=dict)


class ComponentHealth(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(ContractModel):
    schema_version: str = "1.0"
    status: ComponentHealth
    components: dict[str, ComponentHealth]


class EvaluationJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvaluationRunRequest(ContractModel):
    schema_version: str = "1.0"
    reason: str = Field(default="manual", min_length=1, max_length=200)


class EvaluationMetricSummary(ContractModel):
    config_id: str = Field(min_length=3)
    metric: str = Field(min_length=1)
    domain: Domain | None = None
    count: int = Field(ge=0)
    mean_score: float = Field(ge=0.0, le=1.0)


class EvaluationSummary(ContractModel):
    schema_version: str = "1.0"
    job_id: str = Field(min_length=8)
    completed_at: datetime
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    matrix_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_label: str = Field(min_length=1)
    configuration_count: int = Field(ge=1)
    metrics: tuple[EvaluationMetricSummary, ...] = ()


class EvaluationJobAccepted(ContractModel):
    schema_version: str = "1.0"
    job_id: str = Field(min_length=8)
    status: EvaluationJobState


class EvaluationJobStatus(ContractModel):
    schema_version: str = "1.0"
    job_id: str = Field(min_length=8)
    status: EvaluationJobState
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: EvaluationSummary | None = None
    error_code: str | None = None


class SafeErrorResponse(ContractModel):
    schema_version: str = "1.0"
    request_id: str = Field(min_length=8, max_length=128)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


def utc_now() -> datetime:
    return datetime.now(UTC)
