from __future__ import annotations

from pathlib import Path

import pytest

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.retrieval.dense import (
    DenseIndexConfig,
    LocalHashDenseEmbeddingProvider,
    QdrantDenseIndex,
)
from rageval.retrieval.hybrid import HybridRetriever
from rageval.retrieval.hybrid.models import HybridSearchResponse
from rageval.retrieval.rerank import DeterministicFakeReranker, RerankingEngine
from rageval.retrieval.service import MultiHopMode, RetrievalService, RetrievalServiceConfig
from rageval.retrieval.sparse import BM25SparseIndex, SparseDocumentInput, SparseIndexConfig

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "corpus"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}


class _StaticPlanner:
    def __init__(self, second_query: str) -> None:
        self.second_query = second_query

    async def should_multi_hop(self, query: str, first_hop: HybridSearchResponse) -> bool:
        return True

    async def derive_queries(
        self,
        query: str,
        first_hop: HybridSearchResponse,
        *,
        max_queries: int,
    ) -> tuple[str, ...]:
        return (self.second_query,)[:max_queries]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_pipeline_reranks_top5_and_multihop_recovers_non_adjacent_chunk() -> None:
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
            collection_base="rageval_phase9_integration",
            collection_version="test_v1",
            vector_size=provider.dimension,
            exact_search=True,
        ),
    )
    sparse_inputs: list[SparseDocumentInput] = []
    all_chunks = []
    chunks_by_name: dict[str, tuple[object, ...]] = {}
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
            chunks = tuple(chunked.chunks)
            chunks_by_name[Path(item.relative_path).name] = chunks
            all_chunks.extend(chunks)
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
            config=SparseIndexConfig(index_version="phase9_test_v1"),
        )
        hybrid = HybridRetriever(dense=dense, sparse=sparse)
        assert len(all_chunks) >= 5
        forced = all_chunks[-1]
        service = RetrievalService(
            hybrid=hybrid,
            reranker=RerankingEngine(provider=DeterministicFakeReranker({forced.text: 100.0})),
            config=RetrievalServiceConfig(final_top_n=5),
        )
        response = await service.search(all_chunks[0].text)
        assert len(response.final_context) == 5
        assert response.final_context[0].retrieval.chunk == forced
        assert response.final_context[0].metadata["post_rerank_rank"] == 1
        assert response.final_context[0].metadata["pre_rerank_rank"] != 1
        assert response.final_context[0].retrieval.chunk.metadata.get("source_element_ids")

        legal_chunks = chunks_by_name["msa.docx"]
        assert len(legal_chunks) >= 2
        first_legal = legal_chunks[0]
        second_legal = legal_chunks[1]
        single_hop = RetrievalService(
            hybrid=hybrid,
            reranker=RerankingEngine(provider=DeterministicFakeReranker()),
            config=RetrievalServiceConfig(hybrid_top_k=1, final_top_n=1),
        )
        single = await single_hop.search(first_legal.text)
        assert single.final_context[0].retrieval.chunk.chunk_id == first_legal.chunk_id
        assert all(
            item.retrieval.chunk.chunk_id != second_legal.chunk_id for item in single.final_context
        )

        multi_hop = RetrievalService(
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
            multi_hop_planner=_StaticPlanner(second_legal.text),
        )
        multi = await multi_hop.search(first_legal.text)
        assert multi.multi_hop.triggered is True
        assert len(multi.hop_traces) == 2
        assert multi.final_context[0].retrieval.chunk.chunk_id == second_legal.chunk_id
        assert {item.retrieval.chunk.chunk_id for item in multi.final_context} == {
            first_legal.chunk_id,
            second_legal.chunk_id,
        }
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()
