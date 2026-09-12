"""Versioned contracts for Phase 7 sparse indexing and lexical retrieval."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from rageval.models import contracts as model_contracts

DEFAULT_STOPWORDS = (
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "were",
    "with",
)


class BM25Variant(StrEnum):
    """Supported lexical scoring variants."""

    BM25 = "bm25"
    BM25_PLUS = "bm25_plus"


class SparseTokenizerConfig(model_contracts.ContractModel):
    """Deterministic tokenizer behavior included in sparse-index identity."""

    schema_version: str = "1.0"
    lowercase: bool = True
    remove_stopwords: bool = True
    stopwords: tuple[str, ...] = DEFAULT_STOPWORDS


class SparseIndexConfig(model_contracts.ContractModel):
    """Behavior-complete BM25/BM25+ index configuration."""

    schema_version: str = "1.0"
    index_version: str = Field(default="v1", pattern=r"^[A-Za-z0-9_-]+$")
    variant: BM25Variant = BM25Variant.BM25_PLUS
    k1: float = Field(default=1.2, gt=0.0)
    b: float = Field(default=0.75, ge=0.0, le=1.0)
    delta: float = Field(default=1.0, ge=0.0)
    default_top_k: int = Field(default=20, ge=1, le=1000)
    tokenizer: SparseTokenizerConfig = Field(default_factory=SparseTokenizerConfig)


class SparseSearchFilter(model_contracts.ContractModel):
    """Filters supported by the in-process lexical index."""

    domain: model_contracts.Domain | None = None
    document_id: str | None = Field(default=None, min_length=8)
    date_from: date | None = None
    date_to: date | None = None
    chunking_config_fingerprint: str | None = Field(default=None, min_length=16)

    @model_validator(mode="after")
    def validate_date_range(self) -> SparseSearchFilter:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be <= date_to")
        return self


class SparseDocumentInput(model_contracts.ContractModel):
    """Canonical document metadata paired with its Phase 5 chunks."""

    document: model_contracts.DocumentRecord
    chunks: tuple[model_contracts.Chunk, ...]
    source_date: date | None = None


class SparseIndexEntry(model_contracts.ContractModel):
    """Persisted lexical representation for one canonical chunk."""

    chunk: model_contracts.Chunk
    domain: model_contracts.Domain
    source_date: date | None = None
    tokens: tuple[str, ...]
    term_frequencies: dict[str, int]
    document_length: int = Field(ge=0)


class SparseIndexSnapshot(model_contracts.ContractModel):
    """Portable deterministic sparse-index snapshot."""

    schema_version: str = "1.0"
    config: SparseIndexConfig
    config_fingerprint: str = Field(min_length=16)
    index_fingerprint: str = Field(min_length=16)
    entries: tuple[SparseIndexEntry, ...]
    document_frequencies: dict[str, int]
    average_document_length: float = Field(ge=0.0)
    document_count: int = Field(ge=0)


class SparseMatchDiagnostic(model_contracts.ContractModel):
    """Per-result lexical matching evidence for debugging and audits."""

    chunk_id: str = Field(min_length=8)
    rank: int = Field(ge=1)
    score: float = Field(ge=0.0)
    matched_terms: tuple[str, ...]
    term_frequencies: dict[str, int]


class SparseSearchResponse(model_contracts.ContractModel):
    """Stable sparse-search response with query-token and term-match diagnostics."""

    schema_version: str = "1.0"
    query: str
    query_tokens: tuple[str, ...]
    results: tuple[model_contracts.RetrievalResult, ...]
    diagnostics: tuple[SparseMatchDiagnostic, ...]
    index_fingerprint: str = Field(min_length=16)
    config_fingerprint: str = Field(min_length=16)
    index_version: str = Field(min_length=1)
    variant: BM25Variant
    total_latency_ms: float = Field(ge=0.0)
    filters: SparseSearchFilter
