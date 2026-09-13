from __future__ import annotations

from pathlib import Path

import pytest

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

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "corpus"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}
UNANSWERABLE_QUESTION = "What is the lunar population of Europa in 2125?"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_retrieval_service_to_grounded_answer_and_refusal() -> None:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    selected = sorted(
        (item for item in manifest.documents if Path(item.relative_path).name in SELECTED_FIXTURES),
        key=lambda item: item.relative_path,
    )
    chunk_config = reference_chunking_config(ChunkStrategy.FIXED_512)
    provider = LocalHashDenseEmbeddingProvider(dimension=64)
    dense = QdrantDenseIndex(
        provider=provider,
        config=DenseIndexConfig(
            collection_base="rageval_phase10_integration",
            collection_version="test_v1",
            vector_size=provider.dimension,
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

        assert all_chunks
        sparse = BM25SparseIndex.build(
            sparse_inputs,
            config=SparseIndexConfig(index_version="phase10_test_v1"),
        )
        retrieval = RetrievalService(
            hybrid=HybridRetriever(dense=dense, sparse=sparse),
            reranker=RerankingEngine(provider=DeterministicFakeReranker()),
            config=RetrievalServiceConfig(final_top_n=5),
        )
        generation_provider = DeterministicFakeGenerationProvider(
            refuse_questions=[UNANSWERABLE_QUESTION]
        )
        engine = GroundedGenerationEngine(
            provider=generation_provider,
            assembler=ContextAssembler(config=ContextAssemblyConfig(max_context_tokens=600)),
        )
        service = GroundedGenerationService(
            retrieval_service=retrieval,
            engine=engine,
        )

        answerable = await service.answer(all_chunks[0].text)
        assert answerable.answer.insufficient_context is False
        assert answerable.answer.citations
        assert answerable.context is not None
        allowed = set(answerable.context.included_chunk_ids)
        assert allowed
        assert set(answerable.answer.cited_chunk_ids).issubset(allowed)
        assert all(citation.chunk_id in allowed for citation in answerable.answer.citations)
        assert answerable.retrieval is not None
        retrieval_ids = {
            result.retrieval.chunk.chunk_id for result in answerable.retrieval.final_context
        }
        assert set(answerable.answer.cited_chunk_ids).issubset(retrieval_ids)
        assert answerable.answer.metadata["retrieval_service_config_fingerprint"]
        assert answerable.answer.metadata["context_config_fingerprint"]

        refused = await service.answer(UNANSWERABLE_QUESTION)
        assert refused.answer.insufficient_context is True
        assert "Insufficient context" in refused.answer.answer
        assert refused.answer.citations == []
        assert refused.answer.cited_chunk_ids == []
        assert refused.answer.refusal_reason
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()
