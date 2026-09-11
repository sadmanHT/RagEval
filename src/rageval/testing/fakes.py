"""Deterministic provider implementations for acceptance tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rageval.models.contracts import (
    Chunk,
    GroundedAnswer,
    RerankResult,
    RetrievalResult,
)


class FakeEmbeddingProvider:
    name = "fake-embedding"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(map(ord, text)) % 997)] for text in texts]


class FakeRerankerProvider:
    name = "fake-reranker"

    async def rerank(
        self, query: str, candidates: Sequence[RetrievalResult], top_n: int
    ) -> list[RerankResult]:
        del query
        ranked = sorted(candidates, key=lambda item: (-item.score, item.chunk.chunk_id))[:top_n]
        return [
            RerankResult(
                retrieval=item,
                rerank_score=item.score,
                rank=index,
                reranker=self.name,
            )
            for index, item in enumerate(ranked, start=1)
        ]


class FakeGenerationProvider:
    name = "fake-generation"

    async def generate(self, question: str, context: Sequence[Chunk]) -> GroundedAnswer:
        if not context:
            return GroundedAnswer(
                question=question,
                answer="Insufficient context.",
                citations=[],
                insufficient_context=True,
                provider=self.name,
                model="deterministic-v1",
                latency_ms=0,
            )
        return GroundedAnswer(
            question=question,
            answer=context[0].text,
            citations=[],
            insufficient_context=False,
            provider=self.name,
            model="deterministic-v1",
            latency_ms=0,
        )


class FakeTraceProvider:
    name = "fake-trace"

    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, object]]] = []

    async def record(self, event: str, payload: Mapping[str, object]) -> None:
        self.events.append((event, payload))


class FakeExperimentTracker:
    name = "fake-experiment"

    def __init__(self) -> None:
        self.runs: list[tuple[str, Mapping[str, float], Mapping[str, object]]] = []

    async def log_metrics(
        self,
        run_name: str,
        metrics: Mapping[str, float],
        metadata: Mapping[str, object],
    ) -> None:
        self.runs.append((run_name, metrics, metadata))
