"""Typed contracts for chunking strategies and ablation evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from rageval.models.contracts import Chunk, ContractModel, DocumentRecord, Domain


class ChunkStrategy(StrEnum):
    """Reference chunking strategies evaluated by RAG-Eval."""

    FIXED_256 = "fixed_256"
    FIXED_512 = "fixed_512"
    FIXED_1024 = "fixed_1024"
    SEMANTIC = "semantic"


class ChunkingConfig(ContractModel):
    """Versioned configuration that fully determines chunking behavior."""

    schema_version: str = "1.0"
    chunker_version: str = "phase5-1.0"
    strategy: ChunkStrategy = ChunkStrategy.FIXED_512
    chunk_size: int = Field(default=512, ge=1)
    overlap: int = Field(default=64, ge=0)
    semantic_similarity_threshold: float = Field(default=0.78, ge=-1.0, le=1.0)
    semantic_min_tokens: int = Field(default=64, ge=1)
    semantic_max_tokens: int = Field(default=512, ge=1)
    table_aware: bool = True
    repeat_table_header: bool = True
    section_aware: bool = True
    preserve_legal_clauses: bool = True
    tokenizer_name: str = Field(default="whitespace-v1", min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> ChunkingConfig:
        """Keep fixed and semantic boundaries coherent."""
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        if self.semantic_min_tokens > self.semantic_max_tokens:
            raise ValueError("semantic_min_tokens must be <= semantic_max_tokens")
        return self


class ChunkingResult(ContractModel):
    """Chunks emitted for one cleaned document."""

    document: DocumentRecord
    config: ChunkingConfig
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: tuple[Chunk, ...]
    metadata: dict[str, object] = Field(default_factory=dict)


class TokenLengthStats(ContractModel):
    """Token-length distribution produced by an ablation run."""

    count: int = Field(ge=0)
    minimum: int = Field(ge=0)
    maximum: int = Field(ge=0)
    mean: float = Field(ge=0.0)
    p50: float = Field(ge=0.0)
    p95: float = Field(ge=0.0)


class ChunkingStats(ContractModel):
    """Measured chunk statistics for one strategy/domain slice."""

    strategy: ChunkStrategy
    domain: Domain
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    token_lengths: TokenLengthStats
    mean_overlap_tokens: float = Field(ge=0.0)
    table_fragmentation_count: int = Field(ge=0)
    provenance_coverage: float = Field(ge=0.0, le=1.0)


class AblationReport(ContractModel):
    """Machine-readable evidence from a real fixture or corpus ablation run."""

    schema_version: str = "1.0"
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    configs: tuple[ChunkingConfig, ...]
    stats: tuple[ChunkingStats, ...]
    metadata: dict[str, object] = Field(default_factory=dict)


def reference_chunking_config(strategy: ChunkStrategy) -> ChunkingConfig:
    """Return the documented fixed defaults or the semantic baseline configuration."""
    if strategy is ChunkStrategy.FIXED_256:
        return ChunkingConfig(strategy=strategy, chunk_size=256, overlap=32)
    if strategy is ChunkStrategy.FIXED_512:
        return ChunkingConfig(strategy=strategy, chunk_size=512, overlap=64)
    if strategy is ChunkStrategy.FIXED_1024:
        return ChunkingConfig(strategy=strategy, chunk_size=1024, overlap=128)
    return ChunkingConfig(
        strategy=strategy,
        chunk_size=512,
        overlap=0,
        semantic_min_tokens=64,
        semantic_max_tokens=512,
    )
