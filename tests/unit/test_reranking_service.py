from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest

from rageval.core.errors import ProviderError
from rageval.models.contracts import Chunk, RetrievalResult
from rageval.retrieval.hybrid import HybridSearchFilter
from rageval.retrieval.hybrid.models import HybridSearchResponse
from rageval.retrieval.rerank import (
    CohereReranker,
    DeterministicFakeReranker,
    RerankConfig,
    RerankProviderResult,
    RerankingEngine,
)
from rageval.retrieval.service import MultiHopMode, RetrievalService, RetrievalServiceConfig


def _candidate(chunk_id: str, rank: int, text: str, score: float = 0.01) -> RetrievalResult:
    return RetrievalResult(
        chunk=Chunk(
            chunk_id=chunk_id,
            document_id="doc_12345678",
            ordinal=rank - 1,
            text=text,
            token_count=max(1, len(text.split())),
            config_fingerprint="a" * 64,
            metadata={"source_element_ids": [f"el_{rank:08d}"]},
        ),
        score=score,
        rank=rank,
        retriever="hybrid-rrf",
        metadata={"dense_rank": rank, "sparse_rank": rank},
    )


def _hybrid_response(query: str, candidates: Sequence[RetrievalResult]) -> HybridSearchResponse:
    return HybridSearchResponse(
        query=query,
        retrieval_query=query,
        expansions=(),
        results=tuple(candidates),
        diagnostics=(),
        config_fingerprint="b" * 64,
        retriever_version="phase8-1.0",
        rrf_k=60,
        dense_latency_ms=1.0,
        sparse_latency_ms=1.0,
        total_latency_ms=1.5,
        filters=HybridSearchFilter(),
    )


@pytest.mark.asyncio
async def test_fake_reranker_changes_order_and_preserves_original_retrieval() -> None:
    candidates = (
        _candidate("chk_00000001", 1, "baseline context"),
        _candidate("chk_00000002", 2, "preferred evidence"),
    )
    engine = RerankingEngine(
        provider=DeterministicFakeReranker({"preferred": 10.0}),
        config=RerankConfig(final_top_n=2),
    )
    response = await engine.rerank("question", candidates)
    assert [item.retrieval.chunk.chunk_id for item in response.results] == [
        "chk_00000002",
        "chk_00000001",
    ]
    assert response.results[0].metadata["pre_rerank_rank"] == 2
    assert response.results[0].metadata["post_rerank_rank"] == 1
    assert response.results[0].retrieval.metadata["dense_rank"] == 2


@pytest.mark.asyncio
async def test_reranker_ties_are_deterministic_by_pre_rank_then_chunk_id() -> None:
    candidates = (
        _candidate("chk_00000002", 2, "same"),
        _candidate("chk_00000001", 1, "same"),
    )
    engine = RerankingEngine(provider=DeterministicFakeReranker())
    response = await engine.rerank("unmatched", candidates, top_n=2)
    assert [item.retrieval.rank for item in response.results] == [1, 2]


class _BadProvider:
    name = "bad"
    model = "bad-v1"

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> tuple[RerankProviderResult, ...]:
        return (
            RerankProviderResult(index=0, score=1.0),
            RerankProviderResult(index=0, score=0.5),
        )


@pytest.mark.asyncio
async def test_reranking_engine_rejects_duplicate_provider_indexes() -> None:
    engine = RerankingEngine(provider=_BadProvider())
    with pytest.raises(ProviderError, match="duplicate"):
        await engine.rerank("q", (_candidate("chk_00000001", 1, "text"),), top_n=2)


@pytest.mark.asyncio
async def test_cohere_adapter_parses_request_and_response() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.4},
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.cohere.test/v2"
    ) as client:
        provider = CohereReranker(api_key="test-only", client=client)
        results = await provider.rerank("query", ["a", "b"], top_n=2)
    assert [(item.index, item.score) for item in results] == [(1, 0.9), (0, 0.4)]
    assert '"top_n":2' in str(captured["body"]).replace(" ", "")


@pytest.mark.asyncio
async def test_cohere_adapter_retries_rate_limit_with_bounded_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, json={"message": "slow down"})
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.8}]})

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.cohere.test/v2"
    ) as client:
        provider = CohereReranker(
            api_key="test-only",
            client=client,
            max_attempts=3,
            backoff_base_seconds=0.1,
            sleep=fake_sleep,
        )
        results = await provider.rerank("q", ["doc"], top_n=1)
    assert results[0].score == 0.8
    assert attempts == 3
    assert sleeps == [0.1, 0.2]


@pytest.mark.asyncio
async def test_cohere_adapter_timeout_stops_after_max_attempts() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timeout", request=request)

    async def fake_sleep(delay: float) -> None:
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.cohere.test/v2"
    ) as client:
        provider = CohereReranker(
            api_key="test-only",
            client=client,
            max_attempts=2,
            backoff_base_seconds=0.0,
            sleep=fake_sleep,
        )
        with pytest.raises(ProviderError, match="after 2 attempts"):
            await provider.rerank("q", ["doc"], top_n=1)
    assert attempts == 2


class _FakeHybrid:
    def __init__(self, responses: dict[str, HybridSearchResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: HybridSearchFilter | None = None,
    ) -> HybridSearchResponse:
        self.calls.append(query)
        return self.responses[query]


@pytest.mark.asyncio
async def test_simple_query_does_not_trigger_rule_multihop() -> None:
    first = _hybrid_response(
        "What is revenue?", (_candidate("chk_00000001", 1, "Revenue grew."),)
    )
    hybrid = _FakeHybrid({"What is revenue?": first})
    service = RetrievalService(
        hybrid=hybrid,
        reranker=RerankingEngine(provider=DeterministicFakeReranker()),
        config=RetrievalServiceConfig(multi_hop_mode=MultiHopMode.RULE),
    )
    response = await service.search("  What   is revenue? ")
    assert response.normalized_query == "What is revenue?"
    assert response.multi_hop.triggered is False
    assert len(response.hop_traces) == 1
    assert hybrid.calls == ["What is revenue?"]


@pytest.mark.asyncio
async def test_multihop_recovers_non_adjacent_referenced_chunk_and_traces_hops() -> None:
    query = "How does the covenant affect the remedy?"
    first_candidate = _candidate(
        "chk_00000001",
        1,
        "The covenant applies to enterprise customers. See Section 9.2 for remedies.",
    )
    second_candidate = _candidate(
        "chk_00000002",
        1,
        "Section 9.2 provides the termination remedy after covenant breach.",
    )
    hybrid = _FakeHybrid(
        {
            query: _hybrid_response(query, (first_candidate,)),
            "Section 9.2": _hybrid_response("Section 9.2", (second_candidate,)),
        }
    )
    service = RetrievalService(
        hybrid=hybrid,
        reranker=RerankingEngine(
            provider=DeterministicFakeReranker({"termination remedy": 10.0})
        ),
        config=RetrievalServiceConfig(
            multi_hop_mode=MultiHopMode.RULE,
            max_second_hop_queries=1,
            final_top_n=2,
        ),
    )
    response = await service.search(query)
    assert response.multi_hop.triggered is True
    assert response.multi_hop.derived_queries == ("Section 9.2",)
    assert len(response.hop_traces) == 2
    assert [item.retrieval.chunk.chunk_id for item in response.final_context] == [
        "chk_00000002",
        "chk_00000001",
    ]
    assert response.final_context[0].retrieval.metadata["retrieval_service_hops"] == [2]


@pytest.mark.asyncio
async def test_off_mode_keeps_single_hop_even_when_reference_exists() -> None:
    query = "How does the covenant affect the remedy?"
    hybrid = _FakeHybrid(
        {
            query: _hybrid_response(
                query,
                (
                    _candidate(
                        "chk_00000001",
                        1,
                        "See Section 9.2 for remedies.",
                    ),
                ),
            )
        }
    )
    service = RetrievalService(
        hybrid=hybrid,
        reranker=RerankingEngine(provider=DeterministicFakeReranker()),
    )
    response = await service.search(query)
    assert response.multi_hop.mode == MultiHopMode.OFF
    assert response.multi_hop.triggered is False
    assert hybrid.calls == [query]
