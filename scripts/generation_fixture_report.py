"""Emit deterministic Phase 10 grounded-generation fixture evidence as JSON."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
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

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "corpus"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}
UNANSWERABLE_QUESTION = "What is the lunar population of Europa in 2125?"


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
            collection_base="rageval_phase10_fixture",
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

        if not all_chunks:
            raise RuntimeError("Phase 10 fixture produced no canonical chunks")
        sparse = BM25SparseIndex.build(
            sparse_inputs,
            config=SparseIndexConfig(index_version="phase10_fixture_v1"),
        )
        retrieval = RetrievalService(
            hybrid=HybridRetriever(dense=dense, sparse=sparse),
            reranker=RerankingEngine(provider=DeterministicFakeReranker()),
            config=RetrievalServiceConfig(final_top_n=5),
        )
        fake_generation = DeterministicFakeGenerationProvider(
            refuse_questions=[UNANSWERABLE_QUESTION]
        )
        engine = GroundedGenerationEngine(
            provider=fake_generation,
            assembler=ContextAssembler(
                config=ContextAssemblyConfig(max_context_tokens=600)
            ),
        )
        service = GroundedGenerationService(
            retrieval_service=retrieval,
            engine=engine,
        )

        answerable_question = all_chunks[0].text
        answerable = await service.answer(answerable_question)
        refused = await service.answer(UNANSWERABLE_QUESTION)
        if answerable.context is None or answerable.retrieval is None:
            raise AssertionError("answerable fixture must retrieve and assemble context")
        allowed_ids = set(answerable.context.included_chunk_ids)
        cited_ids = set(answerable.answer.cited_chunk_ids)
        if answerable.answer.insufficient_context:
            raise AssertionError("answerable fixture unexpectedly refused")
        if not cited_ids or not cited_ids.issubset(allowed_ids):
            raise AssertionError("answerable fixture citations are not traceable to supplied context")
        if not refused.answer.insufficient_context:
            raise AssertionError("unanswerable fixture did not explicitly refuse")
        if refused.answer.citations or refused.answer.cited_chunk_ids:
            raise AssertionError("unanswerable fixture refusal must not cite unsupported evidence")

        return {
            "schema_version": "1.0",
            "source_documents": len(selected),
            "canonical_chunks": len(all_chunks),
            "provider": answerable.answer.provider,
            "model": answerable.answer.model,
            "sparse_index_fingerprint": sparse.snapshot.index_fingerprint,
            "retrieval_service_config_fingerprint": (
                answerable.retrieval.service_config_fingerprint
            ),
            "generation_config_fingerprint": answerable.generation_config_fingerprint,
            "context_config_fingerprint": answerable.context.config_fingerprint,
            "answerable": {
                "question": answerable_question,
                "insufficient_context": answerable.answer.insufficient_context,
                "cited_chunk_ids": answerable.answer.cited_chunk_ids,
                "context_chunk_ids": list(answerable.context.included_chunk_ids),
                "context_tokens": answerable.context.token_count,
                "repair_count": len(answerable.repairs),
            },
            "unanswerable": {
                "question": UNANSWERABLE_QUESTION,
                "insufficient_context": refused.answer.insufficient_context,
                "citations": [
                    citation.model_dump(mode="json") for citation in refused.answer.citations
                ],
                "refusal_reason": refused.answer.refusal_reason,
            },
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
