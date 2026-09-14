"""End-to-end retrieval -> context assembly -> grounded generation orchestration."""

from __future__ import annotations

import time
from typing import Protocol

from rageval.generation.engine import GroundedGenerationEngine
from rageval.generation.models import GroundedGenerationResponse
from rageval.generation.routing import AlwaysRetrieveRouter, RetrievalRouter
from rageval.models.contracts import GroundedAnswer
from rageval.retrieval.hybrid.models import HybridSearchFilter
from rageval.retrieval.service.models import RetrievalServiceResponse


class RetrievalServiceLike(Protocol):
    """Phase 9 retrieval-service boundary consumed by grounded generation."""

    async def search(
        self,
        query: str,
        *,
        filters: HybridSearchFilter | None = None,
    ) -> RetrievalServiceResponse: ...


class GroundedGenerationService:
    """Produce auditable grounded answers from the canonical Phase 9 retrieval service."""

    def __init__(
        self,
        *,
        retrieval_service: RetrievalServiceLike,
        engine: GroundedGenerationEngine,
        router: RetrievalRouter | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.engine = engine
        self.router = router or AlwaysRetrieveRouter()

    async def answer(
        self,
        question: str,
        *,
        filters: HybridSearchFilter | None = None,
    ) -> GroundedGenerationResponse:
        normalized = " ".join(question.split())
        if not normalized:
            raise ValueError("question must not be blank")
        start = time.perf_counter()
        route = await self.router.route(normalized)
        if not route.retrieval_required:
            answer = GroundedAnswer(
                question=question,
                answer=self.engine.config.insufficient_context_answer,
                citations=[],
                cited_chunk_ids=[],
                insufficient_context=True,
                refusal_reason=(
                    "retrieval router chose no retrieval; no grounded answer was generated"
                ),
                provider="none",
                model="none",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                metadata={
                    "retrieval_route": route.model_dump(mode="json"),
                    "faithfulness_guarantee": "not_applicable_no_retrieval",
                    "generation_config_fingerprint": self.engine.config_fingerprint,
                },
            )
            return GroundedGenerationResponse(
                answer=answer,
                retrieval=None,
                context=None,
                route=route,
                repairs=(),
                generation_config_fingerprint=self.engine.config_fingerprint,
                total_latency_ms=(time.perf_counter() - start) * 1000.0,
            )

        retrieval = await self.retrieval_service.search(normalized, filters=filters)
        generated = await self.engine.generate(question, retrieval.final_context)
        answer = generated.answer.model_copy(
            update={
                "metadata": {
                    **generated.answer.metadata,
                    "retrieval_route": route.model_dump(mode="json"),
                    "retrieval_service_config_fingerprint": retrieval.service_config_fingerprint,
                    "rerank_config_fingerprint": retrieval.rerank_config_fingerprint,
                    "multi_hop_triggered": retrieval.multi_hop.triggered,
                    "retrieval_hops": len(retrieval.hop_traces),
                }
            }
        )
        return GroundedGenerationResponse(
            answer=answer,
            retrieval=retrieval,
            context=generated.context,
            route=route,
            repairs=generated.repairs,
            generation_config_fingerprint=generated.config_fingerprint,
            total_latency_ms=(time.perf_counter() - start) * 1000.0,
        )
