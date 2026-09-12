"""Result-only adapter exposing Phase 6 dense search through the common retriever protocol."""

from __future__ import annotations

from rageval.models.contracts import RetrievalResult
from rageval.retrieval.dense.qdrant import QdrantDenseIndex


class DenseRetriever:
    """Thin adapter that preserves QdrantDenseIndex.search while exposing retrieve()."""

    name = "dense-qdrant"

    def __init__(self, index: QdrantDenseIndex) -> None:
        self.index = index

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 20,
    ) -> tuple[RetrievalResult, ...]:
        """Return canonical dense results without discarding the richer search API."""
        return (await self.index.search(query, top_k=top_k)).results
