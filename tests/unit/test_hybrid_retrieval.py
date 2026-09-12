from __future__ import annotations

import asyncio
from datetime import date

import pytest

from rageval.core.errors import RetrievalError
from rageval.models.contracts import Chunk, Domain, RetrievalResult
from rageval.retrieval.dense.models import DenseSearchFilter, DenseSearchResponse
from rageval.retrieval.hybrid import (
    DictionaryQueryExpansionProvider,
    HybridRetrievalConfig,
    HybridRetriever,
    HybridSearchFilter,
    QueryExpansionConfig,
    bound_expansions,
    fuse_rrf,
)
from rageval.retrieval.sparse.models import (
    BM25Variant,
    SparseSearchFilter,
    SparseSearchResponse,
)


def _chunk(chunk_id: str, text: str = "retrieval evidence") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        ordinal=0,
        text=text,
        token_count=max(1, len(text.split())),
        config_fingerprint="f" * 64,
        metadata={"domain": Domain.RESEARCH.value},
    )


def _result(chunk_id: str, rank: int, score: float, retriever: str) -> RetrievalResult:
    return RetrievalResult(
        chunk=_chunk(chunk_id),
        rank=rank,
        score=score,
        retriever=retriever,
    )


def _dense_response(
    query: str,
    results: tuple[RetrievalResult, ...],
    filters: DenseSearchFilter,
) -> DenseSearchResponse:
    return DenseSearchResponse(
        query=query,
        results=results,
        collection_name="fixture__v1",
        provider="fake-dense",
        model="fake-model",
        total_latency_ms=1.0,
        embedding_latency_ms=0.4,
        qdrant_latency_ms=0.6,
        filters=filters,
    )


def _sparse_response(
    query: str,
    results: tuple[RetrievalResult, ...],
    filters: SparseSearchFilter,
) -> SparseSearchResponse:
    return SparseSearchResponse(
        query=query,
        query_tokens=tuple(query.casefold().split()),
        results=results,
        diagnostics=(),
        index_fingerprint="a" * 64,
        config_fingerprint="b" * 64,
        index_version="v1",
        variant=BM25Variant.BM25_PLUS,
        total_latency_ms=1.0,
        filters=filters,
    )


def test_rrf_arithmetic_overlap_and_one_based_ranks() -> None:
    dense = (
        _result("chk_alpha", 1, 0.91, "dense"),
        _result("chk_bravo", 2, 0.81, "dense"),
    )
    sparse = (
        _result("chk_charlie", 1, 4.2, "sparse"),
        _result("chk_alpha", 2, 3.9, "sparse"),
    )
    results, diagnostics = fuse_rrf(dense, sparse, rrf_k=60, top_k=3)
    assert [result.chunk.chunk_id for result in results] == [
        "chk_alpha",
        "chk_charlie",
        "chk_bravo",
    ]
    assert results[0].score == pytest.approx((1 / 61) + (1 / 62))
    assert diagnostics[0].dense_rank == 1
    assert diagnostics[0].sparse_rank == 2
    assert diagnostics[0].dense_rrf_contribution == pytest.approx(1 / 61)
    assert diagnostics[0].sparse_rrf_contribution == pytest.approx(1 / 62)


def test_rrf_ties_are_stable_by_chunk_id() -> None:
    results, _ = fuse_rrf(
        (_result("chk_bravo", 1, 0.9, "dense"),),
        (_result("chk_alpha", 1, 9.0, "sparse"),),
    )
    assert [result.chunk.chunk_id for result in results] == ["chk_alpha", "chk_bravo"]


def test_rrf_deduplicates_repeated_chunk_within_one_branch() -> None:
    repeated = (
        _result("chk_alpha", 1, 0.9, "dense"),
        _result("chk_alpha", 2, 0.8, "dense"),
    )
    results, diagnostics = fuse_rrf(repeated, (), rrf_k=60)
    assert len(results) == 1
    assert results[0].score == pytest.approx(1 / 61)
    assert len(diagnostics[0].contributions) == 1


def test_rrf_missing_branch_remains_valid() -> None:
    results, diagnostics = fuse_rrf((), (_result("chk_sparse", 1, 7.0, "sparse"),))
    assert results[0].chunk.chunk_id == "chk_sparse"
    assert diagnostics[0].dense_rank is None
    assert diagnostics[0].sparse_rank == 1


def test_rrf_rejects_same_id_with_different_canonical_chunk_payload() -> None:
    dense = _result("chk_collision", 1, 0.9, "dense")
    sparse = RetrievalResult(
        chunk=dense.chunk.model_copy(update={"text": "different canonical content"}),
        rank=1,
        score=4.0,
        retriever="sparse",
    )
    with pytest.raises(RetrievalError, match="identity collision"):
        fuse_rrf((dense,), (sparse,))


def test_expansion_bounds_deduplicate_and_never_replace_original() -> None:
    config = QueryExpansionConfig(enabled=True, max_expansions=2, max_expansion_chars=8)
    assert bound_expansions(
        "turnover",
        [" revenue ", "Revenue", "very-long-expansion", "turnover"],
        config,
    ) == ("revenue", "very-lon")


class _FakeDense:
    def __init__(self, results: tuple[RetrievalResult, ...] = ()) -> None:
        self.results = results
        self.query: str | None = None
        self.filters: DenseSearchFilter | None = None

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: DenseSearchFilter | None = None,
    ) -> DenseSearchResponse:
        self.query = query
        self.filters = filters
        active = filters or DenseSearchFilter()
        return _dense_response(query, self.results[:top_k], active)


class _FakeSparse:
    def __init__(self, results: tuple[RetrievalResult, ...] = ()) -> None:
        self.results = results
        self.query: str | None = None
        self.filters: SparseSearchFilter | None = None

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SparseSearchFilter | None = None,
    ) -> SparseSearchResponse:
        self.query = query
        self.filters = filters
        active = filters or SparseSearchFilter()
        limit = 20 if top_k is None else top_k
        return _sparse_response(query, self.results[:limit], active)


@pytest.mark.asyncio
async def test_hybrid_applies_equivalent_filters_to_both_branches() -> None:
    dense = _FakeDense((_result("chk_filter", 1, 0.9, "dense"),))
    sparse = _FakeSparse((_result("chk_filter", 1, 4.0, "sparse"),))
    retriever = HybridRetriever(dense=dense, sparse=sparse)
    filters = HybridSearchFilter(
        domain=Domain.RESEARCH,
        document_id="doc_filter_001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
        chunking_config_fingerprint="c" * 64,
    )
    response = await retriever.search("retrieval", filters=filters)
    assert dense.filters is not None and sparse.filters is not None
    assert dense.filters.model_dump(mode="json") == sparse.filters.model_dump(mode="json")
    assert response.results[0].metadata["dense_rank"] == 1
    assert response.results[0].metadata["sparse_rank"] == 1


@pytest.mark.asyncio
async def test_query_expansion_is_observable_bounded_and_preserves_original_query() -> None:
    dense = _FakeDense()

    class ExpansionAwareSparse(_FakeSparse):
        async def search(
            self,
            query: str,
            *,
            top_k: int | None = None,
            filters: SparseSearchFilter | None = None,
        ) -> SparseSearchResponse:
            self.query = query
            active = filters or SparseSearchFilter()
            results = (
                (_result("chk_revenue", 1, 5.0, "sparse"),)
                if "revenue" in query.casefold()
                else ()
            )
            return _sparse_response(query, results, active)

    sparse = ExpansionAwareSparse()
    provider = DictionaryQueryExpansionProvider({"turnover": ["revenue", "sales"]})
    retriever = HybridRetriever(
        dense=dense,
        sparse=sparse,
        expansion_provider=provider,
        config=HybridRetrievalConfig(
            expansion=QueryExpansionConfig(enabled=True, max_expansions=1)
        ),
    )
    response = await retriever.search("quarterly turnover")
    assert response.expansions == ("revenue",)
    assert response.retrieval_query.startswith("quarterly turnover")
    assert response.retrieval_query.endswith("revenue")
    assert response.results[0].chunk.chunk_id == "chk_revenue"


@pytest.mark.asyncio
async def test_dense_only_semantic_path_and_sparse_only_exact_path_both_fuse() -> None:
    dense_only = HybridRetriever(
        dense=_FakeDense((_result("chk_semantic", 1, 0.88, "dense"),)),
        sparse=_FakeSparse(),
    )
    semantic = await dense_only.search("conceptual representation query")
    assert semantic.results[0].chunk.chunk_id == "chk_semantic"
    assert semantic.diagnostics[0].sparse_rank is None

    sparse_only = HybridRetriever(
        dense=_FakeDense(),
        sparse=_FakeSparse((_result("chk_zx91", 1, 7.4, "sparse"),)),
    )
    lexical = await sparse_only.search("ZX-91")
    assert lexical.results[0].chunk.chunk_id == "chk_zx91"
    assert lexical.diagnostics[0].dense_rank is None


@pytest.mark.asyncio
async def test_branches_are_started_concurrently() -> None:
    dense_started = asyncio.Event()
    sparse_started = asyncio.Event()

    class CoordinatedDense(_FakeDense):
        async def search(
            self,
            query: str,
            *,
            top_k: int = 10,
            filters: DenseSearchFilter | None = None,
        ) -> DenseSearchResponse:
            dense_started.set()
            await sparse_started.wait()
            return await super().search(query, top_k=top_k, filters=filters)

    class CoordinatedSparse(_FakeSparse):
        async def search(
            self,
            query: str,
            *,
            top_k: int | None = None,
            filters: SparseSearchFilter | None = None,
        ) -> SparseSearchResponse:
            sparse_started.set()
            await dense_started.wait()
            return await super().search(query, top_k=top_k, filters=filters)

    retriever = HybridRetriever(dense=CoordinatedDense(), sparse=CoordinatedSparse())
    response = await asyncio.wait_for(retriever.search("concurrency"), timeout=0.5)
    assert response.results == ()
    assert dense_started.is_set() and sparse_started.is_set()


@pytest.mark.asyncio
async def test_branch_failure_cancels_sibling_and_raises_typed_retrieval_error() -> None:
    sibling_cancelled = asyncio.Event()

    class FailingDense(_FakeDense):
        async def search(
            self,
            query: str,
            *,
            top_k: int = 10,
            filters: DenseSearchFilter | None = None,
        ) -> DenseSearchResponse:
            del query, top_k, filters
            raise RuntimeError("dense boom")

    class WaitingSparse(_FakeSparse):
        async def search(
            self,
            query: str,
            *,
            top_k: int | None = None,
            filters: SparseSearchFilter | None = None,
        ) -> SparseSearchResponse:
            del query, top_k, filters
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                sibling_cancelled.set()
                raise

    retriever = HybridRetriever(dense=FailingDense(), sparse=WaitingSparse())
    with pytest.raises(RetrievalError, match="hybrid branch retrieval failed"):
        await retriever.search("failure")
    assert sibling_cancelled.is_set()


@pytest.mark.asyncio
async def test_latency_instrumentation_does_not_change_result_determinism() -> None:
    dense = _FakeDense((_result("chk_same", 1, 0.9, "dense"),))
    sparse = _FakeSparse((_result("chk_same", 1, 6.0, "sparse"),))
    retriever = HybridRetriever(dense=dense, sparse=sparse)
    first = await retriever.search("same")
    second = await retriever.search("same")
    assert first.results == second.results
    assert first.diagnostics == second.diagnostics
    assert first.dense_latency_ms >= 0
    assert first.sparse_latency_ms >= 0
    assert first.total_latency_ms >= max(first.dense_latency_ms, first.sparse_latency_ms)
