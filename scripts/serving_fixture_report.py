"""Run Phase 13 API fixture against real local Qdrant and Redis."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
from pydantic import SecretStr

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.core.settings import Settings
from rageval.corpus.manifest import scan_corpus
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
from rageval.generation import (
    ContextAssembler,
    ContextAssemblyConfig,
    DeterministicFakeGenerationProvider,
    GroundedGenerationEngine,
    GroundedGenerationService,
)
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Chunk
from rageval.retrieval.dense import (
    DenseIndexConfig,
    LocalHashDenseEmbeddingProvider,
    QdrantDenseIndex,
)
from rageval.retrieval.hybrid import HybridRetriever
from rageval.retrieval.rerank import DeterministicFakeReranker, RerankingEngine
from rageval.retrieval.service import RetrievalService, RetrievalServiceConfig
from rageval.retrieval.sparse import BM25SparseIndex, SparseDocumentInput, SparseIndexConfig
from rageval.serving import (
    QueryCacheIdentity,
    RedisQueryCache,
    ServingDependencies,
    StaticHealthCheck,
    build_query_cache_key,
    create_app,
)
from rageval.serving.models import EvaluationRunRequest, QueryRequest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "corpus"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}
API_KEY = "phase13-fixture-key"


class FixtureEvaluationExecutor:
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
                config_id="phase13-serving-fixture",
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
            evidence_label="phase13-serving-fixture-mechanics-only",
        )


async def _report() -> dict[str, object]:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    selected = sorted(
        (item for item in manifest.documents if Path(item.relative_path).name in SELECTED_FIXTURES),
        key=lambda item: item.relative_path,
    )
    chunk_config = reference_chunking_config(ChunkStrategy.FIXED_512)
    dense_provider = LocalHashDenseEmbeddingProvider(dimension=64)
    dense = QdrantDenseIndex(
        provider=dense_provider,
        config=DenseIndexConfig(
            collection_base="rageval_phase13_fixture",
            collection_version="v1",
            vector_size=dense_provider.dimension,
            exact_search=True,
        ),
    )
    sparse_inputs: list[SparseDocumentInput] = []
    all_chunks: list[Chunk] = []
    collection_name = dense.config.collection_name
    try:
        if await dense.client.collection_exists(collection_name):
            await dense.client.delete_collection(collection_name)
        await dense.ensure_collection()
        for item in selected:
            parsed = parse_corpus_document(
                item,
                FIXTURE_ROOT,
                config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
            )
            cleaned = clean_parsed_document(parsed)
            chunked = await ChunkingEngine().chunk(cleaned, config=chunk_config)
            all_chunks.extend(chunked.chunks)
            sparse_inputs.append(
                SparseDocumentInput(
                    document=item.record,
                    chunks=chunked.chunks,
                    source_date=item.source_date,
                )
            )
            await dense.upsert_document(
                item.record,
                chunked.chunks,
                source_date=item.source_date,
            )

        sparse = BM25SparseIndex.build(
            sparse_inputs,
            config=SparseIndexConfig(index_version="phase13_fixture_v1"),
        )
        retrieval = RetrievalService(
            hybrid=HybridRetriever(dense=dense, sparse=sparse),
            reranker=RerankingEngine(provider=DeterministicFakeReranker()),
            config=RetrievalServiceConfig(final_top_n=5),
        )
        fake_generation = DeterministicFakeGenerationProvider()
        engine = GroundedGenerationEngine(
            provider=fake_generation,
            assembler=ContextAssembler(config=ContextAssemblyConfig(max_context_tokens=600)),
        )
        service = GroundedGenerationService(retrieval_service=retrieval, engine=engine)
        identity = QueryCacheIdentity(
            index_fingerprint=sparse.snapshot.index_fingerprint,
            retrieval_config_fingerprint=retrieval.config_fingerprint,
            generation_config_fingerprint=engine.config_fingerprint,
            model_version=fake_generation.model,
            prompt_version="phase10-grounding-prompt-v1",
        )
        answerable_question = all_chunks[0].text
        query_payload = QueryRequest(
            question=answerable_question,
            top_k=3,
            options={"include_retrieval_diagnostics": True},
        )
        cache = RedisQueryCache.from_url("redis://localhost:6379/0")
        await cache.client.delete(build_query_cache_key(query_payload, identity))

        async def qdrant_health() -> None:
            await dense.client.get_collections()

        app = create_app(
            dependencies=ServingDependencies(
                query_service=service,
                evaluation_executor=FixtureEvaluationExecutor(),
                cache_identity=identity,
                cache=cache,
                health_checks={
                    "qdrant": qdrant_health,
                    "generation_provider": StaticHealthCheck(),
                },
            ),
            settings=Settings(
                serving_api_key=SecretStr(API_KEY),
                serving_expose_retrieval_diagnostics=True,
            ),
        )
        transport = httpx.ASGITransport(app=app)
        headers = {"X-API-Key": API_KEY}
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                ready = await client.get("/health/ready")
                first = await client.post(
                    "/query",
                    headers=headers,
                    json=query_payload.model_dump(mode="json"),
                )
                second = await client.post(
                    "/query",
                    headers=headers,
                    json=query_payload.model_dump(mode="json"),
                )
                streamed = await client.post(
                    "/query",
                    headers=headers,
                    json={
                        **query_payload.model_dump(mode="json"),
                        "options": {"stream": True, "use_cache": False},
                    },
                )
                created = await client.post("/eval/run", headers=headers, json={})
                job_id = created.json()["job_id"]
                status = None
                for _ in range(100):
                    status = await client.get(f"/eval/jobs/{job_id}", headers=headers)
                    if status.json()["status"] == "succeeded":
                        break
                    await asyncio.sleep(0.01)
                latest = await client.get("/eval/latest", headers=headers)

        first_payload = first.json()
        if ready.status_code != 200:
            raise AssertionError("serving readiness did not validate Qdrant and Redis")
        if first.status_code != 200 or second.status_code != 200:
            raise AssertionError("authenticated query endpoint failed")
        if first_payload["insufficient_context"]:
            raise AssertionError("answerable serving fixture unexpectedly refused")
        cited_ids = set(first_payload["cited_chunk_ids"])
        final_ids = set(first_payload["retrieval"]["final_chunk_ids"])
        if not cited_ids or not cited_ids.issubset(final_ids):
            raise AssertionError("serving citations are not traceable to exposed final context IDs")
        if second.json()["cache_hit"] is not True:
            raise AssertionError("second identical query did not hit Redis cache")
        stream_events = [json.loads(line) for line in streamed.text.splitlines()]
        final_events = [event for event in stream_events if event["event"] == "final"]
        if not final_events or not final_events[-1]["data"]["cited_chunk_ids"]:
            raise AssertionError("streaming final event lost structured citations")
        if status is None or status.json()["status"] != "succeeded":
            raise AssertionError("evaluation job did not reach succeeded status")
        if latest.status_code != 200 or latest.json()["job_id"] != job_id:
            raise AssertionError("latest evaluation endpoint did not expose the completed job")

        changed_identity = identity.model_copy(
            update={"index_fingerprint": hashlib.sha256(b"phase13-changed-index").hexdigest()}
        )
        changed_cache = RedisQueryCache.from_url("redis://localhost:6379/0")
        changed_app = create_app(
            dependencies=ServingDependencies(
                query_service=service,
                evaluation_executor=FixtureEvaluationExecutor(),
                cache_identity=changed_identity,
                cache=changed_cache,
                health_checks={"qdrant": qdrant_health},
            ),
            settings=Settings(serving_api_key=SecretStr(API_KEY)),
        )
        changed_transport = httpx.ASGITransport(app=changed_app)
        generation_calls_before = len(fake_generation.calls)
        async with changed_app.router.lifespan_context(changed_app):
            async with httpx.AsyncClient(
                transport=changed_transport,
                base_url="http://test",
            ) as client:
                invalidated = await client.post(
                    "/query",
                    headers=headers,
                    json=query_payload.model_dump(mode="json"),
                )
        if invalidated.status_code != 200 or invalidated.json()["cache_hit"]:
            raise AssertionError("index fingerprint change did not invalidate cached answer")
        if len(fake_generation.calls) != generation_calls_before + 1:
            raise AssertionError("cache invalidation did not execute grounded generation again")

        return {
            "schema_version": "1.0",
            "source_documents": len(selected),
            "canonical_chunks": len(all_chunks),
            "authenticated_query": True,
            "qdrant_ready": ready.json()["components"]["qdrant"] == "ok",
            "redis_ready": ready.json()["components"]["redis"] == "ok",
            "cache_hit": second.json()["cache_hit"],
            "cache_invalidated_after_index_change": not invalidated.json()["cache_hit"],
            "stream_final_citations": final_events[-1]["data"]["cited_chunk_ids"],
            "evaluation_job_status": status.json()["status"],
            "latest_job_id": latest.json()["job_id"],
            "evidence_label": "phase13-serving-fixture-mechanics-only",
        }
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()


def main() -> None:
    print(json.dumps(asyncio.run(_report()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
