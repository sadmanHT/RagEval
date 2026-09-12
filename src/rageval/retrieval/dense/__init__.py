"""Public Phase 6 dense retrieval API."""

from rageval.retrieval.dense.models import (
    DenseIndexConfig,
    DenseSearchFilter,
    DenseSearchResponse,
    IndexConsistencyReport,
    IndexMutationResult,
)
from rageval.retrieval.dense.providers import (
    DenseEmbeddingProvider,
    LocalHashDenseEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from rageval.retrieval.dense.qdrant import QdrantDenseIndex, point_id_for_chunk

__all__ = [
    "DenseEmbeddingProvider",
    "DenseIndexConfig",
    "DenseSearchFilter",
    "DenseSearchResponse",
    "IndexConsistencyReport",
    "IndexMutationResult",
    "LocalHashDenseEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "QdrantDenseIndex",
    "point_id_for_chunk",
]
