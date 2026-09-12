from __future__ import annotations

import asyncio
import json
from pathlib import Path

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

FIXTURE_ROOT = Path("tests/fixtures/corpus")
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


async def _run() -> dict[str, object]:
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
            collection_base="rageval_phase9_fixture",
            collection_version="ci_v1",
            vector_size=dense_provider.dimension,
            exact_search=True,
        ),
    )
    collection_name = dense.config.collection_name
    sparse_inputs: list[SparseDocumentInput] = []
    all_chunks = []
    chunks_by_name: dict[str, tuple[object, ...]] = {}
    documents: list[dict[str, object]] = []
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
            documents.append(
                {
                    "path": item.relative_path,
                    "document_id": item.record.document_id,
                    "domain": item.record.domain.value,
                    "chunk_count": len(chunks),
                }
            )

        sparse = BM25SparseIndex.build(
            sparse_inputs,
            config=SparseIndexConfig(index_version="phase9_ci_v1"),
        )
        hybrid = HybridRetriever(dense=dense, sparse=sparse)
        if len(all_chunks) < 5:
            raise RuntimeError("Phase 9 fixture requires at least five canonical chunks")

        forced = all_chunks[-1]
        engine = RerankingEngine(provider=DeterministicFakeReranker({forced.text: 100.0}))
        service = RetrievalService(
            hybrid=hybrid,
            reranker=engine,
            config=RetrievalServiceConfig(final_top_n=5),
        )
        first_query = all_chunks[0].text
        final = await service.search(first_query)
        if len(final.final_context) != 5:
            raise RuntimeError("Phase 9 final context did not contain five chunks")
        if final.final_context[0].retrieval.chunk.chunk_id != forced.chunk_id:
            raise RuntimeError(
                "deterministic reranker did not reorder the expected chunk to rank 1"
            )

        legal_chunks = chunks_by_name["msa.docx"]
        if len(legal_chunks) < 2:
            raise RuntimeError("Phase 9 multi-hop fixture requires two legal chunks")
        first_legal, second_legal = legal_chunks[:2]
        multi = RetrievalService(
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
        multi_response = await multi.search(first_legal.text)
        if len(multi_response.hop_traces) != 2:
            raise RuntimeError("Phase 9 multi-hop fixture did not record both hops")
        if multi_response.final_context[0].retrieval.chunk.chunk_id != second_legal.chunk_id:
            raise RuntimeError("Phase 9 second-hop evidence was not reranked to final rank 1")

        return {
            "schema_version": "1.0",
            "document_count": len(selected),
            "indexed_chunk_count": len(all_chunks),
            "chunk_strategy": "fixed_512",
            "dense_provider": dense_provider.name,
            "dense_provider_evidence": "local-hash-diagnostic-only",
            "sparse_index_fingerprint": sparse.index_fingerprint,
            "service_config_fingerprint": final.service_config_fingerprint,
            "rerank_config_fingerprint": final.rerank_config_fingerprint,
            "documents": documents,
            "top5": {
                "query_chunk_id": all_chunks[0].chunk_id,
                "forced_rerank_chunk_id": forced.chunk_id,
                "forced_pre_rerank_rank": final.final_context[0].metadata["pre_rerank_rank"],
                "forced_post_rerank_rank": final.final_context[0].metadata["post_rerank_rank"],
                "final_chunk_ids": [
                    item.retrieval.chunk.chunk_id for item in final.final_context
                ],
            },
            "multi_hop": {
                "triggered": multi_response.multi_hop.triggered,
                "hop_count": len(multi_response.hop_traces),
                "derived_queries": list(multi_response.multi_hop.derived_queries),
                "first_chunk_id": first_legal.chunk_id,
                "second_chunk_id": second_legal.chunk_id,
                "final_chunk_ids": [
                    item.retrieval.chunk.chunk_id for item in multi_response.final_context
                ],
            },
            "provider_validation": {
                "deterministic_reranker": "executed",
                "cohere_live": "not_run_without_credentials",
            },
        }
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()


def main() -> None:
    print(json.dumps(asyncio.run(_run()), sort_keys=True))


if __name__ == "__main__":
    main()
