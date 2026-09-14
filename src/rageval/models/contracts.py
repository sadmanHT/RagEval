"""Canonical, versionable data contracts shared across RAG-Eval subsystems."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Strict immutable base for boundary objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Domain(StrEnum):
    FINANCIAL = "financial"
    LEGAL = "legal"
    RESEARCH = "research"


class SourceType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"


class ElementType(StrEnum):
    TITLE = "title"
    TEXT = "text"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CAPTION = "caption"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_BREAK = "page_break"
    OCR_TEXT = "ocr_text"


class DocumentRecord(ContractModel):
    document_id: str = Field(min_length=8)
    source_uri: str = Field(min_length=1)
    source_type: SourceType
    domain: Domain
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentElement(ContractModel):
    element_id: str = Field(min_length=8)
    document_id: str = Field(min_length=8)
    kind: ElementType
    text: str = ""
    page_number: int | None = Field(default=None, ge=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class Chunk(ContractModel):
    chunk_id: str = Field(min_length=8)
    document_id: str = Field(min_length=8)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    config_fingerprint: str = Field(min_length=16)
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievalResult(ContractModel):
    chunk: Chunk
    score: float
    rank: int = Field(ge=1)
    retriever: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class RerankResult(ContractModel):
    retrieval: RetrievalResult
    rerank_score: float
    rank: int = Field(ge=1)
    reranker: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class Citation(ContractModel):
    chunk_id: str = Field(min_length=8)
    claim: str = Field(min_length=1)


class GroundedAnswer(ContractModel):
    """Stable grounded-answer contract extended in Phase 10 with defaulted audit fields."""

    schema_version: str = "1.1"
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    cited_chunk_ids: list[str] = Field(default_factory=list)
    insufficient_context: bool = False
    refusal_reason: str | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class EvaluationExample(ContractModel):
    example_id: str = Field(min_length=8)
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    domain: Domain
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class EvaluationResult(ContractModel):
    example_id: str = Field(min_length=8)
    metric: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    evaluator: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)
