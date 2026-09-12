"""Sparse BM25/BM25+ retrieval boundary."""

from rageval.retrieval.sparse.bm25 import BM25SparseIndex, sparse_config_fingerprint
from rageval.retrieval.sparse.models import (
    BM25Variant,
    SparseDocumentInput,
    SparseIndexConfig,
    SparseIndexEntry,
    SparseIndexSnapshot,
    SparseMatchDiagnostic,
    SparseSearchFilter,
    SparseSearchResponse,
    SparseTokenizerConfig,
)
from rageval.retrieval.sparse.tokenizer import DomainAwareTokenizer

__all__ = [
    "BM25SparseIndex",
    "BM25Variant",
    "DomainAwareTokenizer",
    "SparseDocumentInput",
    "SparseIndexConfig",
    "SparseIndexEntry",
    "SparseIndexSnapshot",
    "SparseMatchDiagnostic",
    "SparseSearchFilter",
    "SparseSearchResponse",
    "SparseTokenizerConfig",
    "sparse_config_fingerprint",
]
