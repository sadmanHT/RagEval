"""Versioned contracts for Phase 6 dense indexing and retrieval."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from rageval.models.contracts import ContractModel, Domain, RetrievalResult


class DenseIndexConfig(ContractModel):
    """Behavior-complete Qdrant dense-index configuration."""

    schema_version: str = "1.0"
    collection_base: str = Field(default="rageval_dense", pattern=r"^[A-Za-z0-9_-]+$")
    collection_version: str = Field(default="v1", pattern=r"^[A-Za-z0-9_-]+$")
    vector_size: int = Field(ge=1)
    distance: Literal["cosine"] = "cosine"
    embed_batch_size: int = Field(default=64, ge=1, le=2048)
    upsert_batch_size: int = Field(default=64, ge=1, le=2048)
    hnsw_m: int = Field(default=16, ge=4)
    hnsw_ef_construct: int = Field(default=100, ge=4)
    search_hnsw_ef: int = Field(default=128, ge=1)
    exact_search: bool = False
    timeout_seconds: float = Field(default=10.0, gt=0.0)

    @property
    def collection_name(self) -> str:
        """Return the concrete versioned Qdrant collection name."""
        return f"{self.collection_base}__{self.collection_version}"


class DenseSearchFilter(ContractModel):
    """Supported payload filters for dense retrieval."""

    domain: Domain | None = None
    document_id: str | None = Field(default=None, min_length=8)
    date_from: date | None = None
    date_to: date | None = None
    chunking_config_fingerprint: str | None = Field(default=None, min_length=16)

    @model_validator(mode="after")
    def validate_date_range(self) -> DenseSearchFilter:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be <= date_to")
        return self


class DenseSearchResponse(ContractModel):
    """Stable dense-search response with measured latency evidence."""

    schema_version: str = "1.0"
    query: str = Field(min_length=1)
    results: tuple[RetrievalResult, ...]
    collection_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    total_latency_ms: float = Field(ge=0.0)
    embedding_latency_ms: float = Field(ge=0.0)
    qdrant_latency_ms: float = Field(ge=0.0)
    filters: DenseSearchFilter


class IndexMutationResult(ContractModel):
    """Auditable result for document-level index mutations."""

    schema_version: str = "1.0"
    collection_name: str = Field(min_length=1)
    document_id: str = Field(min_length=8)
    chunk_count: int = Field(ge=0)
    operation: Literal["upsert", "replace", "delete"]


class IndexConsistencyReport(ContractModel):
    """Exact expected-versus-indexed chunk identity report for one document."""

    schema_version: str = "1.0"
    collection_name: str = Field(min_length=1)
    document_id: str = Field(min_length=8)
    expected_chunk_ids: tuple[str, ...]
    indexed_chunk_ids: tuple[str, ...]
    missing_chunk_ids: tuple[str, ...]
    extra_chunk_ids: tuple[str, ...]
    consistent: bool
