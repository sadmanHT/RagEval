"""High-precision retrieval service: hybrid retrieval -> rerank -> optional multi-hop."""

from __future__ import annotations

import time
from typing import Protocol

from rageval.core.errors import RetrievalError
from rageval.core.ids import fingerprint_mapping
from rageval.models.contracts import RetrievalResult
from rageval.retrieval.hybrid.models import HybridSearchFilter, HybridSearchResponse
from rageval.retrieval.rerank.engine import RerankingEngine
from rageval.retrieval.service.models import (
    MultiHopDecision,
    MultiHopMode,
    RetrievalHopTrace,
    RetrievalServiceConfig,
    RetrievalServiceResponse,
)
from rageval.retrieval.service.multihop import MultiHopPlanner, ReferenceAwareMultiHopPlanner


class HybridSearchService(Protocol):
    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: HybridSearchFilter | None = None,
    ) -> HybridSearchResponse: ...


def retrieval_service_config_fingerprint(config: RetrievalServiceConfig) -> str:
    """Fingerprint every behavior-affecting orchestration option."""
    return fingerprint_mapping(config.model_dump(mode="json"))


def _trace(hop: int, response: HybridSearchResponse) -> RetrievalHopTrace:
    return RetrievalHopTrace(
        hop=hop,
        query=response.query,
        retrieval_query=response.retrieval_query,
        expansions=response.expansions,
        candidate_chunk_ids=tuple(result.chunk.chunk_id for result in response.results),
        hybrid_config_fingerprint=response.config_fingerprint,
        dense_latency_ms=response.dense_latency_ms,
        sparse_latency_ms=response.sparse_latency_ms,
        total_latency_ms=response.total_latency_ms,
    )


def _merge_candidates(
    hops: list[HybridSearchResponse],
    *,
    limit: int,
) -> tuple[RetrievalResult, ...]:
    selected: dict[str, RetrievalResult] = {}
    hop_numbers: dict[str, list[int]] = {}
    hop_queries: dict[str, list[str]] = {}
    order: list[str] = []
    for hop_number, response in enumerate(hops, start=1):
        for result in response.results:
            chunk_id = result.chunk.chunk_id
            current = selected.get(chunk_id)
            if current is None:
                selected[chunk_id] = result
                order.append(chunk_id)
                hop_numbers[chunk_id] = [hop_number]
                hop_queries[chunk_id] = [response.query]
            else:
                if current.chunk != result.chunk:
                    raise RetrievalError(
                        f"chunk identity collision across retrieval hops for {chunk_id}"
                    )
                hop_numbers[chunk_id].append(hop_number)
                hop_queries[chunk_id].append(response.query)

    merged: list[RetrievalResult] = []
    for chunk_id in order[:limit]:
        result = selected[chunk_id]
        merged.append(
            result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        "retrieval_service_hops": hop_numbers[chunk_id],
                        "retrieval_service_queries": hop_queries[chunk_id],
                    }
                }
            )
        )
    return tuple(merged)


class RetrievalService:
    """Orchestrate normalized hybrid retrieval, reranking, and bounded multi-hop retrieval."""

    def __init__(
        self,
        *,
        hybrid: HybridSearchService,
        reranker: RerankingEngine,
        config: RetrievalServiceConfig | None = None,
        multi_hop_planner: MultiHopPlanner | None = None,
    ) -> None:
        self.hybrid = hybrid
        self.reranker = reranker
        self.config = config or RetrievalServiceConfig()
        self.multi_hop_planner = multi_hop_planner or ReferenceAwareMultiHopPlanner()
        self.config_fingerprint = retrieval_service_config_fingerprint(self.config)

    async def search(
        self,
        query: str,
        *,
        filters: HybridSearchFilter | None = None,
        top_k: int | None = None,
    ) -> RetrievalServiceResponse:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise ValueError("query must not be blank")
        final_top_n = self.config.final_top_n if top_k is None else top_k
        if final_top_n < 1 or final_top_n > self.config.max_merged_candidates:
            raise ValueError(
                "top_k must be between 1 and the configured max_merged_candidates budget"
            )
        start = time.perf_counter()
        first_hop = await self.hybrid.search(
            normalized_query,
            top_k=self.config.hybrid_top_k,
            filters=filters,
        )
        responses = [first_hop]
        traces = [_trace(1, first_hop)]

        should_multi_hop = False
        reason = "multi-hop disabled"
        if self.config.multi_hop_mode == MultiHopMode.ALWAYS:
            should_multi_hop = True
            reason = "multi-hop explicitly enabled"
        elif self.config.multi_hop_mode == MultiHopMode.RULE:
            should_multi_hop = await self.multi_hop_planner.should_multi_hop(
                normalized_query,
                first_hop,
            )
            reason = "rule planner triggered" if should_multi_hop else "rule planner not triggered"

        derived_queries: tuple[str, ...] = ()
        if should_multi_hop:
            derived_queries = await self.multi_hop_planner.derive_queries(
                normalized_query,
                first_hop,
                max_queries=self.config.max_second_hop_queries,
            )
            if not derived_queries:
                should_multi_hop = False
                reason = "multi-hop requested but no bounded second-hop query was derived"
            else:
                for hop_number, second_query in enumerate(derived_queries, start=2):
                    response = await self.hybrid.search(
                        second_query,
                        top_k=self.config.hybrid_top_k,
                        filters=filters,
                    )
                    responses.append(response)
                    traces.append(_trace(hop_number, response))

        merged = _merge_candidates(responses, limit=self.config.max_merged_candidates)
        reranked = await self.reranker.rerank(
            normalized_query,
            merged,
            top_n=final_top_n,
        )
        decision = MultiHopDecision(
            triggered=should_multi_hop,
            mode=self.config.multi_hop_mode,
            reason=reason,
            derived_queries=derived_queries if should_multi_hop else (),
        )
        return RetrievalServiceResponse(
            query=query,
            normalized_query=normalized_query,
            final_context=reranked.results,
            hop_traces=tuple(traces),
            multi_hop=decision,
            service_config_fingerprint=self.config_fingerprint,
            rerank_config_fingerprint=reranked.config_fingerprint,
            total_latency_ms=(time.perf_counter() - start) * 1000.0,
        )
