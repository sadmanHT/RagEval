"""Typed Phase 12 comparative-evaluation and ablation contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from rageval.evaluation.models import EvaluationObservation, EvaluationRun
from rageval.models import Domain
from rageval.models.contracts import ContractModel


class ChunkingStrategy(StrEnum):
    FIXED_256 = "fixed_256"
    FIXED_512 = "fixed_512"
    FIXED_1024 = "fixed_1024"
    SEMANTIC = "semantic"
    TABLE_AWARE = "table_aware"


class RetrievalPipeline(StrEnum):
    DENSE_ONLY = "dense_only"
    HYBRID_RRF = "dense_bm25_rrf"
    HYBRID_RERANK = "hybrid_rerank"


class AblationConfiguration(ContractModel):
    """One fully labeled retrieval/generation configuration in an ablation matrix."""

    schema_version: str = "1.0"
    config_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    retrieval_pipeline: RetrievalPipeline
    chunking_strategy: ChunkingStrategy
    query_expansion: bool = False
    multi_hop: bool = False
    candidate_top_k: int = Field(default=20, ge=1)
    final_top_k: int = Field(default=5, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    provider_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    chunk_config: dict[str, object] = Field(default_factory=dict)
    retrieval_params: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candidate_budget(self) -> AblationConfiguration:
        if self.final_top_k > self.candidate_top_k:
            raise ValueError("final_top_k cannot exceed candidate_top_k")
        return self


class EvaluationMatrix(ContractModel):
    schema_version: str = "1.0"
    configurations: tuple[AblationConfiguration, ...]

    @model_validator(mode="after")
    def validate_matrix(self) -> EvaluationMatrix:
        if not self.configurations:
            raise ValueError("evaluation matrix requires at least one configuration")
        config_ids = [item.config_id for item in self.configurations]
        if len(config_ids) != len(set(config_ids)):
            raise ValueError("evaluation matrix contains duplicate config IDs")
        return self


class EvaluationRunnerConfig(ContractModel):
    schema_version: str = "1.0"
    max_concurrency: int = Field(default=4, ge=1, le=64)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=0.05, ge=0, le=60)


class EvaluationEnvironment(ContractModel):
    """External run identity that must be recorded rather than inferred later."""

    schema_version: str = "1.0"
    git_commit: str = Field(min_length=1)
    corpus_index_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    machine_summary: dict[str, object] = Field(default_factory=dict)


class MetricSlice(ContractModel):
    """One metric aggregate with an explicit sample count and optional domain slice."""

    metric: str = Field(min_length=1)
    domain: Domain | None = None
    count: int = Field(ge=0)
    mean_score: float = Field(ge=0, le=1)


class FailureCategory(StrEnum):
    TABLE_FRAGMENTATION = "table_fragmentation"
    VOCABULARY_MISMATCH = "vocabulary_mismatch"
    LONG_RANGE_REFERENCE = "long_range_reference"
    RETRIEVAL_MISS = "retrieval_miss"
    RERANKER_ERROR = "reranker_error"
    CITATION_FAILURE = "citation_failure"
    GENERATION_UNSUPPORTED_CLAIM = "generation_unsupported_claim"
    UNKNOWN = "unknown"


class FailureAnalysisRecord(ContractModel):
    example_id: str = Field(min_length=8)
    categories: tuple[FailureCategory, ...]
    details: tuple[str, ...] = ()


class ObservationCheckpoint(ContractModel):
    schema_version: str = "1.0"
    example_id: str = Field(min_length=8)
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempts: int = Field(ge=1)
    observation: EvaluationObservation


class ConfigurationRun(ContractModel):
    schema_version: str = "1.0"
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    config: AblationConfiguration
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation: EvaluationRun
    metric_slices: tuple[MetricSlice, ...]
    failures: tuple[FailureAnalysisRecord, ...] = ()
    metadata: dict[str, object] = Field(default_factory=dict)
    resumed_examples: int = Field(default=0, ge=0)
    produced_examples: int = Field(default=0, ge=0)


class ComparativeEvaluationReport(ContractModel):
    schema_version: str = "1.0"
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    matrix_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    runs: tuple[ConfigurationRun, ...]
    evidence_label: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)
