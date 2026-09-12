"""Phase 8 concurrent hybrid retrieval, RRF, and query expansion."""

from rageval.retrieval.hybrid.expansion import (
    DictionaryQueryExpansionProvider,
    QueryExpansionProvider,
    assemble_retrieval_query,
    bound_expansions,
)
from rageval.retrieval.hybrid.models import (
    FusionContribution,
    HybridResultDiagnostic,
    HybridRetrievalConfig,
    HybridSearchFilter,
    HybridSearchResponse,
    QueryExpansionConfig,
)
from rageval.retrieval.hybrid.retriever import HybridRetriever, hybrid_config_fingerprint
from rageval.retrieval.hybrid.rrf import fuse_rrf

__all__ = [
    "DictionaryQueryExpansionProvider",
    "FusionContribution",
    "HybridResultDiagnostic",
    "HybridRetrievalConfig",
    "HybridRetriever",
    "HybridSearchFilter",
    "HybridSearchResponse",
    "QueryExpansionConfig",
    "QueryExpansionProvider",
    "assemble_retrieval_query",
    "bound_expansions",
    "fuse_rrf",
    "hybrid_config_fingerprint",
]
