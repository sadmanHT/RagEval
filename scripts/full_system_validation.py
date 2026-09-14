#!/usr/bin/env python3
"""Adversarial Phase 15 full-system validation over the canonical local RAG stack."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")

import httpx
from pydantic import SecretStr

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.core.errors import ProviderError
from rageval.core.settings import Settings
from rageval.corpus.manifest import scan_corpus
from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation import (
    AblationConfiguration,
    AsyncEvaluationRunner,
    ChunkingStrategy,
    DeterministicRuleJudge,
    EvaluationEngine,
    EvaluationMatrix,
    EvaluationObservation,
    EvaluationRunnerConfig,
    LocalJsonExperimentTracker,
    RetrievalPipeline,
    build_environment,
    load_evaluation_jsonl,
)
from rageval.generation import (
    AlwaysRetrieveRouter,
    ConservativeSelfRAGRouter,
    ContextAssembler,
    ContextAssemblyConfig,
    DeterministicFakeGenerationProvider,
    GroundedGenerationEngine,
    GroundedGenerationService,
    OpenAIGenerationProvider,
)
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Chunk, Citation, Domain, ElementType, GroundedAnswer
from rageval.observability import MemoryTraceSink, OperationalTelemetry
from rageval.retrieval.dense import (
    DenseIndexConfig,
    LocalHashDenseEmbeddingProvider,
    QdrantDenseIndex,
)
from rageval.retrieval.hybrid import (
    DictionaryQueryExpansionProvider,
    HybridRetrievalConfig,
    HybridRetriever,
    QueryExpansionConfig,
)
from rageval.retrieval.rerank import DeterministicFakeReranker, RerankingEngine
from rageval.retrieval.service import MultiHopMode, RetrievalService, RetrievalServiceConfig
from rageval.retrieval.sparse import BM25SparseIndex, SparseDocumentInput, SparseIndexConfig
from rageval.serving import (
    QueryCacheIdentity,
    RedisQueryCache,
    ServingDependencies,
    StaticHealthCheck,
    create_app,
)
from rageval.serving.models import EvaluationRunRequest
from rageval.validation import (
    BenchmarkEvidence,
    EvaluationEvidence,
    FullSystemValidationReport,
    LoadEvidence,
    ScenarioEvidence,
    ValidationStatus,
    summarize_latency,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "corpus"
EVALUATION_FIXTURE = ROOT / "tests" / "fixtures" / "evaluation" / "phase11_records.jsonl"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}
SCANNED_FIXTURE = "scanned_notice.pdf"
UNANSWERABLE_QUESTION = "What is the lunar population of Europa in 2125?"
API_KEY = "phase15-deterministic-local-key"  # pragma: allowlist secret
COLD_SAMPLES = 8
WARM_SAMPLES = 8
CONCURRENT_REQUESTS = 12
CONCURRENCY = 4


class ReviewedFixtureObservationProvider:
    """Produce deterministic observations from the actually reviewed three-record fixture."""

    name = "phase15-reviewed-fixture-observation-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def observe(
        self,
        record: EvaluationDatasetRecord,
        config: AblationConfiguration,
    ) -> EvaluationObservation:
        del config
        self.calls += 1
        example = record.example
        support_ids = tuple(example.supporting_chunk_ids)
        if not support_ids:
            raise ValueError("reviewed fixture example requires supporting chunk IDs")
        context = {chunk_id: example.reference_answer for chunk_id in support_ids}
        return EvaluationObservation(
            example=example,
            answer=GroundedAnswer(
                question=example.question,
                answer=example.reference_answer,
                citations=[
                    Citation(chunk_id=support_ids[0], claim=example.reference_answer)
                ],
                cited_chunk_ids=[support_ids[0]],
                provider=self.name,
                model="deterministic-reviewed-fixture-v1",
                latency_ms=0.0,
            ),
            retrieved_chunk_ids=support_ids,
            context_by_chunk_id=context,
        )


class ReleaseEvaluationExecutor:
    """Run the reviewed fixture through the real checkpointed evaluation runner."""

    def __init__(self, *, output_dir: Path, corpus_index_fingerprint: str) -> None:
        self.records = load_evaluation_jsonl(EVALUATION_FIXTURE)
        self.provider = ReviewedFixtureObservationProvider()
        self.output_dir = output_dir
        self.reports = []
        tracker = LocalJsonExperimentTracker(output_dir / "experiment-tracker.jsonl")
        self.runner = AsyncEvaluationRunner(
            observation_provider=self.provider,
            engine=EvaluationEngine(judge=DeterministicRuleJudge()),
            config=EvaluationRunnerConfig(
                max_concurrency=3,
                max_attempts=2,
                retry_backoff_seconds=0.0,
            ),
            tracker=tracker,
        )
        self.environment = build_environment(
            corpus_index_fingerprint=corpus_index_fingerprint,
            repo_root=ROOT,
        )
        self.matrix = EvaluationMatrix(
            configurations=(
                AblationConfiguration(
                    config_id="phase15-release-baseline",
                    retrieval_pipeline=RetrievalPipeline.HYBRID_RERANK,
                    chunking_strategy=ChunkingStrategy.FIXED_512,
                    provider_versions={
                        "observation": "phase15-reviewed-fixture-observation-v1",
                        "judge": "deterministic-rule/lexical-overlap-v1",
                    },
                    prompt_versions={"judge": "phase11-judge-prompt-v1"},
                    retrieval_params={"fixture_only": True},
                ),
            )
        )

    async def run(self, request: EvaluationRunRequest):
        del request
        report = await self.runner.run_matrix(
            self.records,
            self.matrix,
            environment=self.environment,
            output_dir=self.output_dir,
            evidence_label="phase15-reviewed-three-record-mechanics-only",
            report_metadata={
                "reviewed_records": len(self.records),
                "target_200_available": False,
                "tracker": "local-json",
            },
        )
        self.reports.append(report)
        return report


class StaticPlanner:
    """Derive one deterministic second-hop query for long-range acceptance."""

    def __init__(self, second_query: str) -> None:
        self.second_query = second_query

    async def should_multi_hop(self, query, first_hop) -> bool:
        del query, first_hop
        return True

    async def derive_queries(self, query, first_hop, *, max_queries: int) -> tuple[str, ...]:
        del query, first_hop
        return (self.second_query,)[:max_queries]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=ROOT / "artifacts" / "phase15",
        help="Directory for raw Phase 15 evaluation and validation artifacts.",
    )
    parser.add_argument(
        "--require-ocr",
        action="store_true",
        help="Fail if local Tesseract OCR is unavailable.",
    )
    return parser.parse_args()


def _scenario(
    name: str,
    *,
    domain: Domain | None = None,
    **details: object,
) -> ScenarioEvidence:
    return ScenarioEvidence(
        name=name,
        status=ValidationStatus.PASSED,
        domain=domain,
        details=dict(details),
    )


async def _wait_for_eval(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    job_id: str,
) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(f"/eval/jobs/{job_id}", headers=headers)
        if response.status_code != 200:
            raise AssertionError(f"evaluation status failed with {response.status_code}")
        payload = response.json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        await asyncio.sleep(0.01)
    raise AssertionError("evaluation job did not finish")


def _selected_manifest_items():
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    selected = sorted(
        (
            item
            for item in manifest.documents
            if Path(item.relative_path).name in SELECTED_FIXTURES
        ),
        key=lambda item: item.relative_path,
    )
    if len(selected) != len(SELECTED_FIXTURES):
        raise AssertionError("full-system fixture selection is incomplete")
    return manifest, selected


async def _provider_retry_timeout_evidence() -> dict[str, object]:
    retry_calls = 0

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal retry_calls
        retry_calls += 1
        if retry_calls == 1:
            return httpx.Response(429, request=request, json={"error": {"message": "retry"}})
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "phase15-mocked-openai",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "fixture",
                                    "citations": [],
                                    "insufficient_context": True,
                                    "refusal_reason": "fixture",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(retry_handler),
        base_url="https://fixture.invalid/v1",
    ) as client:
        provider = OpenAIGenerationProvider(
            api_key="phase15-mocked-key",  # pragma: allowlist secret
            client=client,
            max_attempts=2,
            backoff_base_seconds=0.0,
        )
        response = await provider.generate(system_prompt="system", user_prompt="user")
    if retry_calls != 2 or response.input_tokens != 3:
        raise AssertionError("mocked OpenAI retry path did not execute exactly two attempts")

    timeout_calls = 0

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_calls
        timeout_calls += 1
        raise httpx.ReadTimeout("phase15 deterministic timeout", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(timeout_handler),
        base_url="https://fixture.invalid/v1",
    ) as client:
        provider = OpenAIGenerationProvider(
            api_key="phase15-mocked-key",  # pragma: allowlist secret
            client=client,
            max_attempts=2,
            backoff_base_seconds=0.0,
        )
        try:
            await provider.generate(system_prompt="system", user_prompt="user")
        except ProviderError:
            pass
        else:
            raise AssertionError("mocked OpenAI timeout path unexpectedly succeeded")
    if timeout_calls != 2:
        raise AssertionError("mocked OpenAI timeout path did not exhaust two attempts")
    return {"retry_attempts": retry_calls, "timeout_attempts": timeout_calls}


async def _run(args: argparse.Namespace) -> FullSystemValidationReport:
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        serving_api_key=SecretStr(API_KEY),
        serving_expose_retrieval_diagnostics=True,
        serving_query_concurrency=CONCURRENCY,
        serving_rate_limit_requests=10_000,
        qdrant_url=os.environ.get("RAGEVAL_QDRANT_URL", "http://127.0.0.1:6333"),
        redis_url=os.environ.get("RAGEVAL_REDIS_URL", "redis://127.0.0.1:6379/0"),
    )
    _, selected = _selected_manifest_items()
    chunk_config = reference_chunking_config(ChunkStrategy.FIXED_512)
    chunks_by_name: dict[str, tuple[Chunk, ...]] = {}
    all_chunks: list[Chunk] = []
    sparse_inputs: list[SparseDocumentInput] = []
    indexed_documents = []

    dense_provider = LocalHashDenseEmbeddingProvider(dimension=64)
    dense = QdrantDenseIndex(
        provider=dense_provider,
        config=DenseIndexConfig(
            collection_base="rageval_phase15_validation",
            collection_version="v1",
            vector_size=dense_provider.dimension,
            exact_search=True,
        ),
        url=settings.qdrant_url,
    )
    collection_name = dense.config.collection_name
    scenarios: list[ScenarioEvidence] = []
    blocked: list[str] = [
        "representative roughly 12,000-document corpus not supplied",
        "target roughly 200-question reviewed evaluation set not supplied",
        "live OpenAI/Cohere/Langfuse/W&B/RAGAS validation not run without credentials",
        "ColPali/vision-table adapter is not present in the current repository roadmap scope",
        "production load/SLO/cost and statistically significant drift validation remain unrun",
    ]

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
            chunks = tuple(chunked.chunks)
            if not chunks:
                raise AssertionError(f"{item.relative_path} produced no chunks")
            filename = Path(item.relative_path).name
            chunks_by_name[filename] = chunks
            all_chunks.extend(chunks)
            sparse_inputs.append(
                SparseDocumentInput(
                    document=item.record,
                    chunks=chunks,
                    source_date=item.source_date,
                )
            )
            indexed_documents.append((item, chunks))
            await dense.upsert_document(item.record, chunks, source_date=item.source_date)

        sparse = BM25SparseIndex.build(
            sparse_inputs,
            config=SparseIndexConfig(index_version="phase15_validation_v1"),
        )
        hybrid = HybridRetriever(dense=dense, sparse=sparse)
        retrieval = RetrievalService(
            hybrid=hybrid,
            reranker=RerankingEngine(provider=DeterministicFakeReranker()),
            config=RetrievalServiceConfig(final_top_n=5),
        )
        fake_generation = DeterministicFakeGenerationProvider(
            refuse_questions=[UNANSWERABLE_QUESTION]
        )
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
        trace_sink = MemoryTraceSink()
        telemetry = OperationalTelemetry(trace_sink=trace_sink, include_query_text=False)
        evaluation_executor = ReleaseEvaluationExecutor(
            output_dir=args.artifact_dir / "reviewed-evaluation",
            corpus_index_fingerprint=sparse.snapshot.index_fingerprint,
        )
        cache = RedisQueryCache.from_url(settings.redis_url)

        async def qdrant_health() -> None:
            await dense.client.get_collections()

        app = create_app(
            dependencies=ServingDependencies(
                query_service=service,
                evaluation_executor=evaluation_executor,
                cache_identity=identity,
                cache=cache,
                health_checks={
                    "qdrant": qdrant_health,
                    "generation_provider": StaticHealthCheck(),
                },
                telemetry=telemetry,
            ),
            settings=settings,
        )
        transport = httpx.ASGITransport(app=app)
        headers = {"X-API-Key": API_KEY}

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://phase15.test",
            ) as client:
                ready = await client.get("/health/ready")
                if ready.status_code != 200:
                    raise AssertionError("full-system readiness failed before validation")

                domain_sources = {
                    Domain.FINANCIAL: "financial_report.pdf",
                    Domain.LEGAL: "msa.docx",
                    Domain.RESEARCH: "paper.html",
                }
                for domain, filename in domain_sources.items():
                    source_chunk = chunks_by_name[filename][0]
                    response = await client.post(
                        "/query",
                        headers=headers,
                        json={
                            "question": source_chunk.text,
                            "domain": domain.value,
                            "top_k": 5,
                            "options": {
                                "use_cache": False,
                                "include_retrieval_diagnostics": True,
                            },
                        },
                    )
                    payload = response.json()
                    final_ids = set(payload["retrieval"]["final_chunk_ids"])
                    cited_ids = set(payload["cited_chunk_ids"])
                    if (
                        response.status_code != 200
                        or payload["insufficient_context"]
                        or source_chunk.chunk_id not in final_ids
                        or not cited_ids
                        or not cited_ids.issubset(final_ids)
                    ):
                        raise AssertionError(f"{domain.value} full-system scenario failed")
                    scenarios.append(
                        _scenario(
                            f"{domain.value}-domain-e2e",
                            domain=domain,
                            source_chunk_id=source_chunk.chunk_id,
                            cited_chunk_ids=sorted(cited_ids),
                        )
                    )

                table_chunks = [
                    chunk
                    for chunk in chunks_by_name["financial_table.pdf"]
                    if chunk.metadata.get("table_row_group") is True
                ]
                if not table_chunks:
                    raise AssertionError("table-aware fixture produced no table chunk")
                table_chunk = table_chunks[0]
                response = await client.post(
                    "/query",
                    headers=headers,
                    json={
                        "question": table_chunk.text,
                        "domain": Domain.FINANCIAL.value,
                        "top_k": 5,
                        "options": {
                            "use_cache": False,
                            "include_retrieval_diagnostics": True,
                        },
                    },
                )
                payload = response.json()
                if (
                    response.status_code != 200
                    or table_chunk.chunk_id not in payload["retrieval"]["final_chunk_ids"]
                    or not payload["cited_chunk_ids"]
                ):
                    raise AssertionError("table-aware retrieval scenario failed")
                scenarios.append(
                    _scenario(
                        "table-aware-retrieval",
                        domain=Domain.FINANCIAL,
                        table_chunk_id=table_chunk.chunk_id,
                        source_table_id=table_chunk.metadata["source_table_id"],
                    )
                )

                expansion_hybrid = HybridRetriever(
                    dense=dense,
                    sparse=sparse,
                    config=HybridRetrievalConfig(
                        expansion=QueryExpansionConfig(enabled=True, max_expansions=2)
                    ),
                    expansion_provider=DictionaryQueryExpansionProvider(
                        {"rank merger": ("Reciprocal Rank Fusion",)}
                    ),
                )
                expanded = await expansion_hybrid.search("score-free rank merger", top_k=5)
                research_ids = {chunk.chunk_id for chunk in chunks_by_name["paper.html"]}
                expanded_ids = {item.chunk.chunk_id for item in expanded.results}
                if (
                    "Reciprocal Rank Fusion" not in expanded.expansions
                    or not research_ids.intersection(expanded_ids)
                ):
                    raise AssertionError("query expansion did not recover research vocabulary")
                scenarios.append(
                    _scenario(
                        "vocabulary-mismatch-query-expansion",
                        domain=Domain.RESEARCH,
                        expansions=list(expanded.expansions),
                        recovered_chunk_ids=sorted(research_ids.intersection(expanded_ids)),
                    )
                )

                legal_chunks = chunks_by_name["msa.docx"]
                if len(legal_chunks) < 2:
                    raise AssertionError("multi-hop scenario requires at least two legal chunks")
                first_legal, second_legal = legal_chunks[:2]
                multi_service = RetrievalService(
                    hybrid=hybrid,
                    reranker=RerankingEngine(
                        provider=DeterministicFakeReranker({second_legal.text: 100.0})
                    ),
                    config=RetrievalServiceConfig(
                        hybrid_top_k=1,
                        final_top_n=2,
                        multi_hop_mode=MultiHopMode.ALWAYS,
                        max_second_hop_queries=1,
                    ),
                    multi_hop_planner=StaticPlanner(second_legal.text),
                )
                multi_result = await multi_service.search(first_legal.text)
                if (
                    len(multi_result.hop_traces) != 2
                    or multi_result.final_context[0].retrieval.chunk.chunk_id
                    != second_legal.chunk_id
                ):
                    raise AssertionError("multi-hop recovery scenario failed")
                scenarios.append(
                    _scenario(
                        "long-range-multi-hop",
                        domain=Domain.LEGAL,
                        hop_count=len(multi_result.hop_traces),
                        recovered_chunk_id=second_legal.chunk_id,
                    )
                )

                refusal = await client.post(
                    "/query",
                    headers=headers,
                    json={
                        "question": UNANSWERABLE_QUESTION,
                        "options": {"use_cache": False},
                    },
                )
                refusal_payload = refusal.json()
                if (
                    refusal.status_code != 200
                    or not refusal_payload["insufficient_context"]
                    or refusal_payload["cited_chunk_ids"]
                ):
                    raise AssertionError("insufficient-context refusal scenario failed")
                scenarios.append(
                    _scenario(
                        "insufficient-context-refusal",
                        cited_chunk_count=len(refusal_payload["cited_chunk_ids"]),
                    )
                )

                retry_evidence = await _provider_retry_timeout_evidence()
                scenarios.append(
                    _scenario("provider-retry-timeout", **retry_evidence)
                )

                substantive = chunks_by_name["paper.html"][0].text
                always_service = GroundedGenerationService(
                    retrieval_service=retrieval,
                    engine=engine,
                    router=AlwaysRetrieveRouter(),
                )
                selfrag_service = GroundedGenerationService(
                    retrieval_service=retrieval,
                    engine=engine,
                    router=ConservativeSelfRAGRouter(),
                )
                always_answer = await always_service.answer(substantive)
                selfrag_answer = await selfrag_service.answer(substantive)
                smalltalk = await selfrag_service.answer("hello")
                if (
                    not always_answer.route.retrieval_required
                    or not selfrag_answer.route.retrieval_required
                    or not always_answer.answer.cited_chunk_ids
                    or not selfrag_answer.answer.cited_chunk_ids
                    or smalltalk.route.retrieval_required
                    or not smalltalk.answer.insufficient_context
                ):
                    raise AssertionError("Self-RAG comparison violated grounded routing invariants")
                scenarios.append(
                    _scenario(
                        "self-rag-vs-always-retrieve",
                        substantive_both_retrieve=True,
                        smalltalk_refuses_without_retrieval=True,
                        default_router="always-retrieve-v1",
                    )
                )

                first_eval = await client.post(
                    "/eval/run",
                    headers=headers,
                    json={"reason": "phase15-first-reviewed-run"},
                )
                first_status = await _wait_for_eval(
                    client,
                    headers=headers,
                    job_id=first_eval.json()["job_id"],
                )
                second_eval = await client.post(
                    "/eval/run",
                    headers=headers,
                    json={"reason": "phase15-resume-reviewed-run"},
                )
                second_status = await _wait_for_eval(
                    client,
                    headers=headers,
                    job_id=second_eval.json()["job_id"],
                )
                if (
                    first_status["status"] != "succeeded"
                    or second_status["status"] != "succeeded"
                    or len(evaluation_executor.reports) != 2
                ):
                    raise AssertionError("evaluation jobs did not complete twice")
                first_run = evaluation_executor.reports[0].runs[0]
                second_run = evaluation_executor.reports[1].runs[0]
                reviewed_count = len(evaluation_executor.records)
                if (
                    first_run.produced_examples != reviewed_count
                    or first_run.resumed_examples != 0
                    or second_run.resumed_examples != reviewed_count
                    or second_run.produced_examples != 0
                    or evaluation_executor.provider.calls != reviewed_count
                ):
                    raise AssertionError("evaluation checkpoint resume semantics failed")
                scenarios.append(
                    _scenario(
                        "evaluation-resume",
                        reviewed_records=reviewed_count,
                        produced_first=first_run.produced_examples,
                        resumed_second=second_run.resumed_examples,
                    )
                )

                # Rebuild the real dense collection from the same canonical source records.
                await dense.client.delete_collection(collection_name)
                await dense.ensure_collection()
                for item, chunks in indexed_documents:
                    await dense.upsert_document(
                        item.record,
                        chunks,
                        source_date=item.source_date,
                    )
                rebuild_probe = await retrieval.search(chunks_by_name["paper.html"][0].text)
                if not any(
                    result.retrieval.chunk.chunk_id
                    in {chunk.chunk_id for chunk in chunks_by_name["paper.html"]}
                    for result in rebuild_probe.final_context
                ):
                    raise AssertionError("index rebuild did not restore research retrieval")
                scenarios.append(
                    _scenario(
                        "index-rebuild",
                        collection=collection_name,
                        restored_chunks=len(all_chunks),
                    )
                )

                benchmark_question = chunks_by_name["financial_report.pdf"][0].text
                cold_api: list[float] = []
                cold_retrieval: list[float] = []
                cold_generation: list[float] = []
                for _ in range(COLD_SAMPLES):
                    response = await client.post(
                        "/query",
                        headers=headers,
                        json={
                            "question": benchmark_question,
                            "domain": Domain.FINANCIAL.value,
                            "options": {"use_cache": False},
                        },
                    )
                    payload = response.json()
                    if response.status_code != 200 or payload["insufficient_context"]:
                        raise AssertionError("cold benchmark request failed")
                    cold_api.append(payload["latency"]["api_ms"])
                    cold_retrieval.append(payload["latency"]["retrieval_ms"])
                    cold_generation.append(payload["latency"]["generation_ms"])

                warm_payload = {
                    "question": benchmark_question,
                    "domain": Domain.FINANCIAL.value,
                    "options": {"use_cache": True},
                }
                prime = await client.post("/query", headers=headers, json=warm_payload)
                if prime.status_code != 200:
                    raise AssertionError("cache benchmark prime failed")
                warm_api: list[float] = []
                for _ in range(WARM_SAMPLES):
                    response = await client.post("/query", headers=headers, json=warm_payload)
                    payload = response.json()
                    if response.status_code != 200 or payload["cache_hit"] is not True:
                        raise AssertionError("warm cache benchmark did not hit Redis")
                    warm_api.append(payload["latency"]["api_ms"])

                async def concurrent_request() -> float:
                    response = await client.post(
                        "/query",
                        headers=headers,
                        json={
                            "question": substantive,
                            "domain": Domain.RESEARCH.value,
                            "options": {"use_cache": False},
                        },
                    )
                    payload = response.json()
                    if (
                        response.status_code != 200
                        or payload["insufficient_context"]
                        or not payload["cited_chunk_ids"]
                    ):
                        raise AssertionError("concurrent query failed")
                    return float(payload["latency"]["api_ms"])

                wall_start = time.perf_counter()
                concurrent_latencies = await asyncio.gather(
                    *(concurrent_request() for _ in range(CONCURRENT_REQUESTS))
                )
                wall_ms = (time.perf_counter() - wall_start) * 1000.0
                load = LoadEvidence(
                    request_count=CONCURRENT_REQUESTS,
                    concurrency=CONCURRENCY,
                    wall_time_ms=wall_ms,
                    requests_per_second=CONCURRENT_REQUESTS / (wall_ms / 1000.0),
                    latency=summarize_latency(list(concurrent_latencies)),
                )
                scenarios.append(
                    _scenario(
                        "api-modest-concurrency",
                        request_count=CONCURRENT_REQUESTS,
                        concurrency=CONCURRENCY,
                        all_grounded=True,
                    )
                )

                metrics = (await client.get("/metrics")).text
                if (
                    "rageval_http_requests_total" not in metrics
                    or "rageval_evaluation_jobs_total" not in metrics
                    or "rageval_cache_requests_total" not in metrics
                ):
                    raise AssertionError("full-system Prometheus metrics are incomplete")
                kinds = {record.kind for record in trace_sink.records}
                if not {"query", "evaluation"}.issubset(kinds):
                    raise AssertionError("full-system tracing missed query/evaluation linkage")
                trace_payload = "\n".join(
                    record.model_dump_json(exclude_none=True)
                    for record in trace_sink.records
                )
                if benchmark_question in trace_payload or substantive in trace_payload:
                    raise AssertionError("raw query text leaked into redacted trace payload")
                scenarios.append(
                    _scenario(
                        "tracing-and-metrics",
                        trace_records=len(trace_sink.records),
                        trace_kinds=sorted(kinds),
                        raw_query_text_recorded=False,
                    )
                )

                changed_identity = identity.model_copy(
                    update={
                        "index_fingerprint": hashlib.sha256(
                            b"phase15-rebuilt-index-v2"
                        ).hexdigest()
                    }
                )
                changed_cache = RedisQueryCache.from_url(settings.redis_url)
                changed_app = create_app(
                    dependencies=ServingDependencies(
                        query_service=service,
                        evaluation_executor=evaluation_executor,
                        cache_identity=changed_identity,
                        cache=changed_cache,
                        health_checks={"qdrant": qdrant_health},
                    ),
                    settings=settings,
                )
                changed_transport = httpx.ASGITransport(app=changed_app)
                generation_calls_before = len(fake_generation.calls)
                async with changed_app.router.lifespan_context(changed_app):
                    async with httpx.AsyncClient(
                        transport=changed_transport,
                        base_url="http://phase15-cache.test",
                    ) as changed_client:
                        changed = await changed_client.post(
                            "/query",
                            headers=headers,
                            json=warm_payload,
                        )
                if changed.status_code != 200 or changed.json()["cache_hit"]:
                    raise AssertionError("index identity change did not invalidate Redis cache")
                if len(fake_generation.calls) != generation_calls_before + 1:
                    raise AssertionError("cache invalidation did not re-run generation")
                scenarios.append(
                    _scenario(
                        "cache-invalidation-after-index-identity-change",
                        cache_hit=False,
                    )
                )

                benchmark = BenchmarkEvidence(
                    environment={
                        "python": sys.version.split()[0],
                        "platform": platform.platform(),
                        "machine": platform.machine(),
                        "source_documents": len(selected),
                        "canonical_chunks": len(all_chunks),
                        "cold_samples": COLD_SAMPLES,
                        "warm_samples": WARM_SAMPLES,
                    },
                    cold_api=summarize_latency(cold_api),
                    cold_retrieval=summarize_latency(cold_retrieval),
                    cold_generation=summarize_latency(cold_generation),
                    warm_cache_api=summarize_latency(warm_api),
                    concurrent_api=load,
                    methodology=(
                        "Local deterministic fixture measurements inside the validation process; "
                        "cold requests disable cache, warm requests require Redis hits, and stage "
                        "latencies come from the typed API response. These are not production SLOs."
                    ),
                )

        # OCR is validated after the main app closes so it remains independent of cache state.
        tesseract_available = shutil.which("tesseract") is not None
        if args.require_ocr and not tesseract_available:
            raise AssertionError("--require-ocr requested but Tesseract is unavailable")
        if tesseract_available:
            manifest = scan_corpus(FIXTURE_ROOT).manifest
            scanned = next(
                item
                for item in manifest.documents
                if Path(item.relative_path).name == SCANNED_FIXTURE
            )
            parsed = parse_corpus_document(
                scanned,
                FIXTURE_ROOT,
                config=ParserConfig(ocr_mode=OCRMode.FALLBACK, detect_tables=True),
            )
            if not parsed.used_ocr or not any(
                element.text.strip()
                for element in parsed.elements
                if element.kind is not ElementType.PAGE_BREAK
            ):
                raise AssertionError("scanned legal fixture did not execute OCR successfully")
            scenarios.append(
                _scenario(
                    "local-ocr-scanned-legal",
                    domain=Domain.LEGAL,
                    used_ocr=parsed.used_ocr,
                )
            )
        else:
            blocked.append("local OCR not run in this invocation because Tesseract is unavailable")

        final_evaluation_run = evaluation_executor.reports[-1].runs[0].evaluation
        hallucination = final_evaluation_run.hallucination
        evaluation = EvaluationEvidence(
            reviewed_record_count=len(evaluation_executor.records),
            target_200_available=False,
            dataset_fingerprint=final_evaluation_run.dataset_fingerprint,
            hallucination_flagged_count=hallucination.flagged_count,
            hallucination_total_count=hallucination.total_count,
            hallucination_rate=hallucination.rate,
            resumed_examples=evaluation_executor.reports[-1].runs[0].resumed_examples,
            produced_examples_first_run=evaluation_executor.reports[0].runs[0].produced_examples,
            tracker="local-json",
        )
        provider_validation = {
            "local_hash_embeddings": "executed",
            "deterministic_reranker": "executed",
            "deterministic_generation": "executed",
            "openai_retry_timeout_mock_transport": "executed",
            "openai_live": "blocked_no_credentials",
            "cohere_live": "blocked_no_credentials",
            "langfuse_live": "blocked_no_credentials",
            "wandb_live": "blocked_no_credentials",
            "ragas_live": "blocked_not_configured",
        }
        report = FullSystemValidationReport(
            git_commit=os.environ.get("GITHUB_SHA", "unknown"),
            evidence_label="phase15-local-full-system-fixture-evidence-only",
            source_documents=len(selected),
            canonical_chunks=len(all_chunks),
            scenarios=tuple(scenarios),
            benchmark=benchmark,
            evaluation=evaluation,
            provider_validation=provider_validation,
            blocked_validations=tuple(blocked),
            release_gate_passed=(
                all(item.status is ValidationStatus.PASSED for item in scenarios)
                and (tesseract_available or not args.require_ocr)
            ),
        )
        (args.artifact_dir / "full-system-validation.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()


def main() -> None:
    args = _parse_args()
    report = asyncio.run(_run(args))
    print(report.model_dump_json(indent=2))
    if not report.release_gate_passed:
        raise SystemExit("Phase 15 deterministic release gate did not pass")


if __name__ == "__main__":
    main()
