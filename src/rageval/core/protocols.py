"""Provider protocols that keep external SDKs outside core application logic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from rageval.models.contracts import Chunk, GroundedAnswer, RerankResult, RetrievalResult


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in input order."""
        ...


@runtime_checkable
class RerankerProvider(Protocol):
    name: str

    async def rerank(
        self, query: str, candidates: Sequence[RetrievalResult], top_n: int
    ) -> list[RerankResult]:
        """Rerank retrieval candidates and return at most top_n results."""
        ...


@runtime_checkable
class GenerationProvider(Protocol):
    name: str

    async def generate(self, question: str, context: Sequence[Chunk]) -> GroundedAnswer:
        """Generate a grounded answer from supplied context only."""
        ...


@runtime_checkable
class TraceProvider(Protocol):
    name: str

    async def record(self, event: str, payload: Mapping[str, object]) -> None:
        """Record an observable event."""
        ...


@runtime_checkable
class ExperimentTracker(Protocol):
    name: str

    async def log_metrics(
        self,
        run_name: str,
        metrics: Mapping[str, float],
        metadata: Mapping[str, object],
    ) -> None:
        """Persist evaluation metrics and run metadata."""
        ...
