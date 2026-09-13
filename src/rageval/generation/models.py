"""Versioned contracts for grounded generation, context assembly, repair, and routing."""

from __future__ import annotations

from pydantic import Field

from rageval.models.contracts import Citation, ContractModel, GroundedAnswer, RerankResult
from rageval.retrieval.service.models import RetrievalServiceResponse


class ContextAssemblyConfig(ContractModel):
    """Behavior-complete configuration for deterministic context assembly."""

    schema_version: str = "1.0"
    assembler_version: str = Field(default="phase10-1.0", min_length=1)
    max_context_tokens: int = Field(default=1200, ge=32, le=100_000)
    near_duplicate_jaccard_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    min_truncated_chunk_tokens: int = Field(default=8, ge=1, le=10_000)
    tokenizer_name: str = Field(default="whitespace-v1", min_length=1)


class ContextChunk(ContractModel):
    """One chunk as rendered into the grounded-generation context."""

    chunk_id: str = Field(min_length=8)
    document_id: str = Field(min_length=8)
    rank: int = Field(ge=1)
    text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    source_metadata: dict[str, object] = Field(default_factory=dict)
    truncated: bool = False


class AssembledContext(ContractModel):
    """Deterministic bounded context plus omission/deduplication diagnostics."""

    schema_version: str = "1.0"
    rendered: str = ""
    chunks: tuple[ContextChunk, ...] = ()
    included_chunk_ids: tuple[str, ...] = ()
    omitted_chunk_ids: tuple[str, ...] = ()
    duplicate_chunk_ids: tuple[str, ...] = ()
    token_count: int = Field(default=0, ge=0)
    config_fingerprint: str = Field(min_length=16)


class LLMProviderResponse(ContractModel):
    """Raw provider response retained until application-side validation succeeds."""

    content: str = Field(min_length=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class ProviderGroundedPayload(ContractModel):
    """Structured payload expected from an LLM before citation validation."""

    answer: str = Field(min_length=1)
    citations: tuple[Citation, ...] = ()
    insufficient_context: bool = False
    refusal_reason: str | None = None


class GenerationConfig(ContractModel):
    """Behavior-complete grounded-generation validation and repair policy."""

    schema_version: str = "1.0"
    generation_version: str = Field(default="phase10-1.0", min_length=1)
    max_repair_attempts: int = Field(default=1, ge=0, le=3)
    require_citations: bool = True
    insufficient_context_answer: str = Field(
        default="Insufficient context: the retrieved evidence does not support an answer.",
        min_length=1,
    )


class GenerationRepair(ContractModel):
    """One bounded repair attempt triggered by invalid structured output."""

    attempt: int = Field(ge=1)
    reason: str = Field(min_length=1)
    invalid_output_excerpt: str = Field(min_length=1, max_length=500)


class GenerationEngineResult(ContractModel):
    """Validated grounded answer plus assembly/repair diagnostics."""

    answer: GroundedAnswer
    context: AssembledContext
    repairs: tuple[GenerationRepair, ...] = ()
    config_fingerprint: str = Field(min_length=16)


class RetrievalRouteDecision(ContractModel):
    """Observable Self-RAG-style decision about whether retrieval is required."""

    retrieval_required: bool
    router: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class GroundedGenerationResponse(ContractModel):
    """End-to-end retrieval-to-generation response with auditable diagnostics."""

    schema_version: str = "1.0"
    answer: GroundedAnswer
    retrieval: RetrievalServiceResponse | None = None
    context: AssembledContext | None = None
    route: RetrievalRouteDecision
    repairs: tuple[GenerationRepair, ...] = ()
    generation_config_fingerprint: str = Field(min_length=16)
    total_latency_ms: float = Field(ge=0.0)


class GroundedContextInput(ContractModel):
    """Typed wrapper used by deterministic fixtures that already have reranked context."""

    question: str = Field(min_length=1)
    context: tuple[RerankResult, ...]
