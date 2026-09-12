"""Concurrent dense+sparse retrieval with observable Reciprocal Rank Fusion."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol

from rageval.core.errors import RetrievalError
from rageval.core.ids import fingerprint_mapping
from rageval.models.contracts import RetrievalResult
from rageval.retrieval.dense.models import DenseSearchFilter, DenseSearchResponse
from rageval.retrieval.hybrid.expansion import (
    QueryExpansionProvider,
    assemble_retrieval_query,
    bound_expansions,
)
from rageval.retrieval.hybrid.models import (
    HybridRetrievalConfig,
    HybridSearchFilter,
    HybridSearchResponse,
)
from rageval.retrieval.hybrid.rrf import fuse_rrf
from rageval.retrieval.sparse.models import SparseSearchFilter, SparseSearchResponse


class DenseSearchBackend(Protocol):
    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: DenseSearchFilter | None = None,
    ) -> DenseSearchResponse: ...


class SparseSearchBackend(Protocol):
    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SparseSearchFilter | None = None,
    ) -> SparseSearchResponse: ...


def hybrid_config_fingerprint(config: HybridRetrievalConfig) -> str:
    """Fingerprint every behavior-affecting hybrid retrieval option."""
    return fingerprint_mapping(config.model_dump(mode="json"))


def _dense_filter(filters: HybridSearchFilter) -> DenseSearchFilter:
    return DenseSearchFilter(
        domain=filters.domain,
        document_id=filters.document_id,
        date_from=filters.date_from,
        date_to=filters.date_to,
        chunking_config_fingerprint=filters.chunking_config_fingerprint,
    )


def _sparse_filter(filters: HybridSearchFilter) -> SparseSearchFilter:
    return SparseSearchFilter(
        domain=filters.domain,
        document_id=filters.document_id,
        date_from=filters.date_from,
        date_to=filters.date_to,
        chunking_config_fingerprint=filters.chunking_config_fingerprint,
    )


class HybridRetriever:
    """Central retriever that runs dense and sparse branches concurrently and fuses by rank."""

    name = "hybrid-rrf"

    def __init__(
        self,
        *,
        dense: DenseSearchBackend,
        sparse: SparseSearchBackend,
        config: HybridRetrievalConfig | None = None,
        expansion_provider: QueryExpansionProvider | None = None,
    ) -> None:
        self.dense = dense
        self.sparse = sparse
        self.config = config or HybridRetrievalConfig()
        self.expansion_provider = expansion_provider
        if self.config.expansion.enabled and expansion_provider is None:
            raise ValueError("enabled query expansion requires an expansion provider")
        self.config_fingerprint = hybrid_config_fingerprint(self.config)

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 20,
    ) -> tuple[RetrievalResult, ...]:
        """Common retriever projection using concurrent branch retrieval."""
        return (await self.search(query, top_k=top_k)).results

    async def _expand(self, query: str) -> tuple[str, ...]:
        if not self.config.expansion.enabled:
            return ()
        provider = self.expansion_provider
        if provider is None:
            raise RetrievalError("query expansion is enabled without a provider")
        try:
            proposed = await provider.expand(
                query,
                max_expansions=self.config.expansion.max_expansions,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise RetrievalError(f"query expansion failed: {exc}") from exc
        return bound_expansions(query, proposed, self.config.expansion)

    async def _dense_call(
        self,
        query: str,
        filters: HybridSearchFilter,
    ) -> tuple[DenseSearchResponse, float]:
        start = time.perf_counter()
        response = await self.dense.search(
            query,
            top_k=self.config.branch_top_k,
            filters=_dense_filter(filters),
        )
        return response, (time.perf_counter() - start) * 1000.0

    async def _sparse_call(
        self,
        query: str,
        filters: HybridSearchFilter,
    ) -> tuple[SparseSearchResponse, float]:
        start = time.perf_counter()
        response = await self.sparse.search(
            query,
            top_k=self.config.branch_top_k,
            filters=_sparse_filter(filters),
        )
        return response, (time.perf_counter() - start) * 1000.0

    async def _branches_concurrent(
        self,
        query: str,
        filters: HybridSearchFilter,
    ) -> tuple[tuple[DenseSearchResponse, float], tuple[SparseSearchResponse, float]]:
        dense_task = asyncio.create_task(self._dense_call(query, filters))
        sparse_task = asyncio.create_task(self._sparse_call(query, filters))
        try:
            dense_pair, sparse_pair = await asyncio.gather(dense_task, sparse_task)
            return dense_pair, sparse_pair
        except asyncio.CancelledError:
            dense_task.cancel()
            sparse_task.cancel()
            await asyncio.gather(dense_task, sparse_task, return_exceptions=True)
            raise
        except Exception as exc:
            dense_task.cancel()
            sparse_task.cancel()
            await asyncio.gather(dense_task, sparse_task, return_exceptions=True)
            raise RetrievalError(f"hybrid branch retrieval failed: {exc}") from exc

    async def _branches_sequential(
        self,
        query: str,
        filters: HybridSearchFilter,
    ) -> tuple[tuple[DenseSearchResponse, float], tuple[SparseSearchResponse, float]]:
        try:
            dense_pair = await self._dense_call(query, filters)
            sparse_pair = await self._sparse_call(query, filters)
            return dense_pair, sparse_pair
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise RetrievalError(f"hybrid branch retrieval failed: {exc}") from exc

    async def _search(
        self,
        query: str,
        *,
        top_k: int | None,
        filters: HybridSearchFilter | None,
        concurrent: bool,
    ) -> HybridSearchResponse:
        if not query.strip():
            raise ValueError("query must not be blank")
        active_top_k = self.config.final_top_k if top_k is None else top_k
        if active_top_k < 1:
            raise ValueError("top_k must be positive")
        active_filters = filters or HybridSearchFilter()
        total_start = time.perf_counter()
        expansions = await self._expand(query)
        retrieval_query = assemble_retrieval_query(query, expansions)
        if concurrent:
            dense_pair, sparse_pair = await self._branches_concurrent(
                retrieval_query,
                active_filters,
            )
        else:
            dense_pair, sparse_pair = await self._branches_sequential(
                retrieval_query,
                active_filters,
            )
        dense_response, dense_latency_ms = dense_pair
        sparse_response, sparse_latency_ms = sparse_pair
        fused, diagnostics = fuse_rrf(
            dense_response.results,
            sparse_response.results,
            rrf_k=self.config.rrf_k,
            top_k=active_top_k,
        )
        enriched = tuple(
            result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        "hybrid_config_fingerprint": self.config_fingerprint,
                        "retrieval_query": retrieval_query,
                        "expansions": list(expansions),
                    }
                }
            )
            for result in fused
        )
        return HybridSearchResponse(
            query=" ".join(query.split()),
            retrieval_query=retrieval_query,
            expansions=expansions,
            results=enriched,
            diagnostics=diagnostics,
            config_fingerprint=self.config_fingerprint,
            retriever_version=self.config.retriever_version,
            rrf_k=self.config.rrf_k,
            dense_latency_ms=dense_latency_ms,
            sparse_latency_ms=sparse_latency_ms,
            total_latency_ms=(time.perf_counter() - total_start) * 1000.0,
            filters=active_filters,
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: HybridSearchFilter | None = None,
    ) -> HybridSearchResponse:
        """Run the production concurrent hybrid retrieval path."""
        return await self._search(query, top_k=top_k, filters=filters, concurrent=True)

    async def search_sequential(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: HybridSearchFilter | None = None,
    ) -> HybridSearchResponse:
        """Run the same branches sequentially for local latency comparison evidence only."""
        return await self._search(query, top_k=top_k, filters=filters, concurrent=False)
