"""Versioned contracts for Phase 9 reranking."""

from __future__ import annotations

from pydantic import Field

from rageval.models.contracts import ContractModel, RerankResult


class RerankProviderResult(ContractModel):
    """Provider score for one candidate document by input index."""

    index: int = Field(ge=0)
    score: float


class RerankConfig(ContractModel):
    """Behavior-affecting reranking configuration."""

    schema_version: str = "1.0"
    reranker_version: str = Field(default="phase9-1.0", min_length=1)
    final_top_n: int = Field(default=5, ge=1, le=100)


class RerankResponse(ContractModel):
    """Auditable reranking response preserving original retrieval objects."""

    schema_version: str = "1.0"
    query: str = Field(min_length=1)
    results: tuple[RerankResult, ...]
    input_count: int = Field(ge=0)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    config_fingerprint: str = Field(min_length=16)
    latency_ms: float = Field(ge=0.0)
