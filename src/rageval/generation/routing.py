"""Observable retrieval routing for grounded generation."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from rageval.generation.models import RetrievalRouteDecision


@runtime_checkable
class RetrievalRouter(Protocol):
    """Decide whether grounded generation must retrieve evidence first."""

    name: str

    async def route(self, question: str) -> RetrievalRouteDecision: ...


class AlwaysRetrieveRouter:
    """Safe default: domain questions always retrieve before generation."""

    name = "always-retrieve-v1"

    async def route(self, question: str) -> RetrievalRouteDecision:
        del question
        return RetrievalRouteDecision(
            retrieval_required=True,
            router=self.name,
            reason="grounded generation defaults to retrieval",
        )


class ConservativeSelfRAGRouter:
    """Only skip retrieval for an intentionally tiny set of obvious small-talk utterances."""

    name = "conservative-self-rag-v1"
    _SMALL_TALK = frozenset(
        {
            "hello",
            "hi",
            "hey",
            "thanks",
            "thank you",
            "good morning",
            "good afternoon",
            "good evening",
        }
    )

    async def route(self, question: str) -> RetrievalRouteDecision:
        normalized = " ".join(question.casefold().split())
        normalized = re.sub(r"[^a-z ]+", "", normalized).strip()
        if normalized in self._SMALL_TALK:
            return RetrievalRouteDecision(
                retrieval_required=False,
                router=self.name,
                reason="obvious small-talk is outside the grounded domain-answer path",
            )
        return RetrievalRouteDecision(
            retrieval_required=True,
            router=self.name,
            reason="domain or substantive request requires retrieved evidence",
        )
