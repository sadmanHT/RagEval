"""Versioned retrieval-service and multi-hop diagnostics contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from rageval.models.contracts import ContractModel, RerankResult


class MultiHopMode(StrEnum):
    OFF = "off"
    ALWAYS = "always"
    RULE = "rule"


class RetrievalServiceConfig(ContractModel):
    """Behavior-complete Phase 9 retrieval-service configuration."""

    schema_version: str = "1.0"
    service_version: str = Field(default="phase9-1.0", min_length=1)
    hybrid_top_k: int = Field(default=20, ge=1, le=1000)
    final_top_n: int = Field(default=5, ge=1, le=100)
    multi_hop_mode: MultiHopMode = MultiHopMode.OFF
    max_second_hop_queries: int = Field(default=2, ge=1, le=5)
    max_merged_candidates: int = Field(default=40, ge=1, le=200)

    @model_validator(mode="after")
    def validate_candidate_budget(self) -> RetrievalServiceConfig:
        if self.max_merged_candidates < self.final_top_n:
            raise ValueError("max_merged_candidates must be >= final_top_n")
        return self


class RetrievalHopTrace(ContractModel):
    """One auditable hybrid retrieval hop."""

    hop: int = Field(ge=1)
    query: str = Field(min_length=1)
    retrieval_query: str = Field(min_length=1)
    expansions: tuple[str, ...]
    candidate_chunk_ids: tuple[str, ...]
    hybrid_config_fingerprint: str = Field(min_length=16)
    dense_latency_ms: float = Field(ge=0.0)
    sparse_latency_ms: float = Field(ge=0.0)
    total_latency_ms: float = Field(ge=0.0)


class MultiHopDecision(ContractModel):
    """Why multi-hop was or was not executed."""

    triggered: bool
    mode: MultiHopMode
    reason: str = Field(min_length=1)
    derived_queries: tuple[str, ...] = ()


class RetrievalServiceResponse(ContractModel):
    """Final top context plus complete rerank and hop diagnostics."""

    schema_version: str = "1.0"
    query: str = Field(min_length=1)
    normalized_query: str = Field(min_length=1)
    final_context: tuple[RerankResult, ...]
    hop_traces: tuple[RetrievalHopTrace, ...]
    multi_hop: MultiHopDecision
    service_config_fingerprint: str = Field(min_length=16)
    rerank_config_fingerprint: str = Field(min_length=16)
    total_latency_ms: float = Field(ge=0.0)
