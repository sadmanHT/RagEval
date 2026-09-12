"""Chunking strategies, provenance, and ablation evidence."""

from rageval.chunking.ablation import run_chunking_ablation
from rageval.chunking.engine import (
    ChunkingEngine,
    CosineSimilarityPolicy,
    SimilarityPolicy,
    chunk_document,
    chunking_config_fingerprint,
)
from rageval.chunking.models import (
    AblationReport,
    ChunkingConfig,
    ChunkingResult,
    ChunkingStats,
    ChunkStrategy,
    TokenLengthStats,
    reference_chunking_config,
)
from rageval.chunking.providers import LocalHashEmbeddingProvider
from rageval.chunking.tokenizer import Tokenizer, WhitespaceTokenizer

__all__ = [
    "AblationReport",
    "ChunkingConfig",
    "ChunkingEngine",
    "ChunkingResult",
    "ChunkingStats",
    "ChunkStrategy",
    "CosineSimilarityPolicy",
    "LocalHashEmbeddingProvider",
    "SimilarityPolicy",
    "TokenLengthStats",
    "Tokenizer",
    "WhitespaceTokenizer",
    "chunk_document",
    "chunking_config_fingerprint",
    "reference_chunking_config",
    "run_chunking_ablation",
]
