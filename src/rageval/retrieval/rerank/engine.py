"""Canonical reranking engine over Phase 8 fused retrieval results."""

from __future__ import annotations

import time
from collections.abc import Sequence

from rageval.core.errors import ProviderError
from rageval.core.ids import fingerprint_mapping
from rageval.models.contracts import RerankResult, RetrievalResult
from rageval.retrieval.rerank.models import RerankConfig, RerankResponse
from rageval.retrieval.rerank.providers import RerankerProvider


def rerank_config_fingerprint(config: RerankConfig, provider: RerankerProvider) -> str:
    """Fingerprint scoring configuration plus provider/model identity."""
    payload = config.model_dump(mode="json")
    payload["provider"] = provider.name
    payload["model"] = provider.model
    return fingerprint_mapping(payload)


class RerankingEngine:
    """Apply one reranker while preserving each canonical retrieval result intact."""

    def __init__(self, *, provider: RerankerProvider, config: RerankConfig | None = None) -> None:
        self.provider = provider
        self.config = config or RerankConfig()
        self.config_fingerprint = rerank_config_fingerprint(self.config, provider)

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalResult],
        *,
        top_n: int | None = None,
    ) -> RerankResponse:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise ValueError("query must not be blank")
        active_top_n = self.config.final_top_n if top_n is None else top_n
        if active_top_n < 1:
            raise ValueError("top_n must be positive")
        start = time.perf_counter()
        if not candidates:
            return RerankResponse(
                query=normalized_query,
                results=(),
                input_count=0,
                provider=self.provider.name,
                model=self.provider.model,
                config_fingerprint=self.config_fingerprint,
                latency_ms=(time.perf_counter() - start) * 1000.0,
            )

        provider_results = await self.provider.rerank(
            normalized_query,
            [candidate.chunk.text for candidate in candidates],
            top_n=min(active_top_n, len(candidates)),
        )
        seen: set[int] = set()
        validated: list[tuple[int, float]] = []
        for item in provider_results:
            if item.index >= len(candidates):
                raise ProviderError("reranker returned an out-of-range candidate index")
            if item.index in seen:
                raise ProviderError("reranker returned a duplicate candidate index")
            seen.add(item.index)
            validated.append((item.index, item.score))

        validated.sort(
            key=lambda pair: (
                -pair[1],
                candidates[pair[0]].rank,
                candidates[pair[0]].chunk.chunk_id,
            )
        )
        ranked: list[RerankResult] = []
        for post_rank, (index, score) in enumerate(validated[:active_top_n], start=1):
            retrieval = candidates[index]
            ranked.append(
                RerankResult(
                    retrieval=retrieval,
                    rerank_score=score,
                    rank=post_rank,
                    reranker=self.provider.name,
                    metadata={
                        "pre_rerank_rank": retrieval.rank,
                        "post_rerank_rank": post_rank,
                        "provider_result_index": index,
                        "reranker_model": self.provider.model,
                        "rerank_config_fingerprint": self.config_fingerprint,
                    },
                )
            )
        return RerankResponse(
            query=normalized_query,
            results=tuple(ranked),
            input_count=len(candidates),
            provider=self.provider.name,
            model=self.provider.model,
            config_fingerprint=self.config_fingerprint,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )
