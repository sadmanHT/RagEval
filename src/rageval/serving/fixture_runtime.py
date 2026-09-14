"""Deterministic operational ASGI fixture used by Docker/Compose smoke validation.

This module is intentionally not a production-provider bootstrap. It exercises the real HTTP,
Redis-cache, readiness, metrics, tracing, and evaluation-job boundaries while keeping generation
credential-free. Representative retrieval/generation quality remains covered only by explicit
fixture evidence and later real-corpus/provider validation.
"""

from __future__ import annotations

import httpx

from rageval.core.settings import Settings
from rageval.evaluation import (
    AblationConfiguration,
    ChunkingStrategy,
    ComparativeEvaluationReport,
    ConfigurationRun,
    EvaluationRun,
    HallucinationSummary,
    MetricSlice,
    RetrievalPipeline,
)
from rageval.generation import AssembledContext, ContextChunk, GroundedGenerationResponse
from rageval.generation.models import RetrievalRouteDecision
from rageval.models import Citation, Chunk, GroundedAnswer, RerankResult, RetrievalResult
from rageval.retrieval.hybrid.models import HybridSearchFilter
from rageval.retrieval.service.models import (
    MultiHopDecision,
    MultiHopMode,
    RetrievalHopTrace,
    RetrievalServiceResponse,
)
from rageval.serving.app import ServingDependencies, create_app
from rageval.serving.cache import QueryCacheIdentity, RedisQueryCache
from rageval.serving.health import StaticHealthCheck
from rageval.serving.models import EvaluationRunRequest

_CHUNK_ID = "chk_phase14_operational_fixture"
_DOCUMENT_ID = "doc_phase14_operational_fixture"
_SUPPORT_TEXT = "The Phase 14 operational fixture verifies the containerized serving boundary."


class _OperationalQueryService:
    async def answer(
        self,
        question: str,
        *,
        filters: HybridSearchFilter | None = None,
        top_k: int | None = None,
    ) -> GroundedGenerationResponse:
        del filters, top_k
        chunk = Chunk(
            chunk_id=_CHUNK_ID,
            document_id=_DOCUMENT_ID,
            ordinal=0,
            text=_SUPPORT_TEXT,
            token_count=10,
            config_fingerprint="1" * 64,
            metadata={"fixture_only": True},
        )
        retrieval = RetrievalResult(
            chunk=chunk,
            score=0.032,
            rank=1,
            retriever="hybrid-rrf",
            metadata={
                "dense_rank": 1,
                "sparse_rank": 1,
                "dense_rrf_contribution": 0.016,
                "sparse_rrf_contribution": 0.016,
            },
        )
        reranked = RerankResult(
            retrieval=retrieval,
            rerank_score=1.0,
            rank=1,
            reranker="fake",
            metadata={"pre_rerank_rank": 1, "post_rerank_rank": 1},
        )
        retrieval_response = RetrievalServiceResponse(
            query=question,
            normalized_query=" ".join(question.split()),
            final_context=(reranked,),
            hop_traces=(
                RetrievalHopTrace(
                    hop=1,
                    query=question,
                    retrieval_query=question,
                    expansions=(),
                    candidate_chunk_ids=(_CHUNK_ID,),
                    hybrid_config_fingerprint="2" * 64,
                    dense_latency_ms=0.1,
                    sparse_latency_ms=0.1,
                    total_latency_ms=0.2,
                ),
            ),
            multi_hop=MultiHopDecision(
                triggered=False,
                mode=MultiHopMode.OFF,
                reason="deterministic operational fixture",
            ),
            service_config_fingerprint="3" * 64,
            rerank_config_fingerprint="4" * 64,
            total_latency_ms=0.5,
        )
        context = AssembledContext(
            rendered=_SUPPORT_TEXT,
            chunks=(
                ContextChunk(
                    chunk_id=_CHUNK_ID,
                    document_id=_DOCUMENT_ID,
                    rank=1,
                    text=_SUPPORT_TEXT,
                    token_count=10,
                    source_metadata={"fixture_only": True},
                ),
            ),
            included_chunk_ids=(_CHUNK_ID,),
            token_count=10,
            config_fingerprint="5" * 64,
        )
        answer = GroundedAnswer(
            question=question,
            answer=_SUPPORT_TEXT,
            citations=[Citation(chunk_id=_CHUNK_ID, claim=_SUPPORT_TEXT)],
            cited_chunk_ids=[_CHUNK_ID],
            provider="fake",
            model="phase14-operational-fixture-v1",
            input_tokens=10,
            output_tokens=10,
            latency_ms=0.5,
            metadata={"fixture_only": True},
        )
        return GroundedGenerationResponse(
            answer=answer,
            retrieval=retrieval_response,
            context=context,
            route=RetrievalRouteDecision(
                retrieval_required=True,
                router="phase14-operational-fixture",
                reason="fixture route",
            ),
            generation_config_fingerprint="6" * 64,
            total_latency_ms=1.0,
        )


class _OperationalEvaluationExecutor:
    async def run(self, request: EvaluationRunRequest) -> ComparativeEvaluationReport:
        del request
        evaluation = EvaluationRun(
            dataset_fingerprint="a" * 64,
            config_fingerprint="b" * 64,
            run_fingerprint="c" * 64,
            judge_provider="fixture",
            judge_model="fixture-v1",
            records=(),
            aggregates=(),
            hallucination=HallucinationSummary(
                threshold=0.8,
                flagged_count=0,
                total_count=0,
                rate=0.0,
            ),
        )
        run = ConfigurationRun(
            run_id="d" * 64,
            config=AblationConfiguration(
                config_id="phase14-operational-fixture",
                retrieval_pipeline=RetrievalPipeline.HYBRID_RERANK,
                chunking_strategy=ChunkingStrategy.FIXED_512,
            ),
            dataset_fingerprint="a" * 64,
            config_fingerprint="e" * 64,
            evaluation=evaluation,
            metric_slices=(MetricSlice(metric="faithfulness", count=3, mean_score=1.0),),
        )
        return ComparativeEvaluationReport(
            dataset_fingerprint="a" * 64,
            matrix_fingerprint="f" * 64,
            runs=(run,),
            evidence_label="phase14-container-operational-mechanics-only",
        )


settings = Settings()
cache = RedisQueryCache.from_url(settings.redis_url)


async def _qdrant_health() -> None:
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.get(f"{settings.qdrant_url.rstrip('/')}/collections")
        response.raise_for_status()


app = create_app(
    dependencies=ServingDependencies(
        query_service=_OperationalQueryService(),
        evaluation_executor=_OperationalEvaluationExecutor(),
        cache_identity=QueryCacheIdentity(
            index_fingerprint="7" * 64,
            retrieval_config_fingerprint="3" * 64,
            generation_config_fingerprint="6" * 64,
            model_version="phase14-operational-fixture-v1",
            prompt_version="phase14-operational-fixture-prompt-v1",
        ),
        cache=cache,
        health_checks={
            "qdrant": _qdrant_health,
            "generation_provider": StaticHealthCheck(),
        },
    ),
    settings=settings,
)
