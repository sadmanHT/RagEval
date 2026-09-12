"""Versioned contracts for Phase 8 hybrid retrieval and query expansion."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from rageval.models.contracts import ContractModel, Domain, RetrievalResult


class QueryExpansionConfig(ContractModel):
    """Bounded optional query-expansion behavior."""

    schema_version: str = "1.0"
    enabled: bool = False
    max_expansions: int = Field(default=3, ge=0, le=10)
    max_expansion_chars: int = Field(default=160, ge=1, le=1000)


class HybridRetrievalConfig(ContractModel):
    """Behavior-complete configuration for concurrent RRF retrieval."""

    schema_version: str = "1.0"
    retriever_version: str = Field(default="phase8-1.0", min_length=1)
    branch_top_k: int = Field(default=20, ge=1, le=1000)
    final_top_k: int = Field(default=20, ge=1, le=1000)
    rrf_k: int = Field(default=60, ge=1, le=10000)
    expansion: QueryExpansionConfig = Field(default_factory=QueryExpansionConfig)


class HybridSearchFilter(ContractModel):
    """Filter contract applied equivalently to dense and sparse branches."""

    domain: Domain | None = None
    document_id: str | None = Field(default=None, min_length=8)
    date_from: date | None = None
    date_to: date | None = None
    chunking_config_fingerprint: str | None = Field(default=None, min_length=16)

    @model_validator(mode="after")
    def validate_date_range(self) -> HybridSearchFilter:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be <= date_to")
        return self


class FusionContribution(ContractModel):
    """One branch's auditable contribution to a fused chunk."""

    branch: str = Field(pattern=r"^(dense|sparse)$")
    source_rank: int = Field(ge=1)
    source_score: float
    rrf_contribution: float = Field(gt=0.0)


class HybridResultDiagnostic(ContractModel):
    """Per-result dense/sparse rank and RRF evidence."""

    chunk_id: str = Field(min_length=8)
    final_rank: int = Field(ge=1)
    rrf_score: float = Field(gt=0.0)
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_rank: int | None = Field(default=None, ge=1)
    dense_score: float | None = None
    sparse_score: float | None = None
    dense_rrf_contribution: float = Field(default=0.0, ge=0.0)
    sparse_rrf_contribution: float = Field(default=0.0, ge=0.0)
    contributions: tuple[FusionContribution, ...]


class HybridSearchResponse(ContractModel):
    """Stable hybrid-search response with fusion, expansion, and latency diagnostics."""

    schema_version: str = "1.0"
    query: str = Field(min_length=1)
    retrieval_query: str = Field(min_length=1)
    expansions: tuple[str, ...]
    results: tuple[RetrievalResult, ...]
    diagnostics: tuple[HybridResultDiagnostic, ...]
    config_fingerprint: str = Field(min_length=16)
    retriever_version: str = Field(min_length=1)
    rrf_k: int = Field(ge=1)
    dense_latency_ms: float = Field(ge=0.0)
    sparse_latency_ms: float = Field(ge=0.0)
    total_latency_ms: float = Field(ge=0.0)
    filters: HybridSearchFilter
