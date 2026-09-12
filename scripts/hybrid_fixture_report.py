"""Emit reproducible Phase 8 hybrid/RRF/expansion evidence on local fixtures."""

from __future__ import annotations

import asyncio
import json
import statistics
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
from rageval.retrieval.hybrid import (
    DictionaryQueryExpansionProvider,
    HybridRetrievalConfig,
    HybridRetriever,
    HybridSearchFilter,
    QueryExpansionConfig,
)
from rageval.retrieval.sparse import BM25SparseIndex, SparseDocumentInput, SparseIndexConfig

FIXTURE_ROOT = Path(__file__).parents[1] / "tests" / "fixtures" / "corpus"
SELECTED_FIXTURES = (
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
)


async def build_report() -> dict[str, object]:
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
            collection_base="rageval_phase8_fixture",
            collection_version="ci_v1",
            vector_size=provider.dimension,
            exact_search=True,
        ),
    )
    collection_name = dense.config.collection_name
    sparse_inputs: list[SparseDocumentInput] = []
    chunks_by_document: dict[str, tuple[object, ...]] = {}
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
            chunks_by_document[item.record.document_id] = tuple(chunked.chunks)
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
                    "document_id": item.record.document_id,
                    "domain": item.record.domain.value,
                    "path": item.relative_path,
                    "chunk_count": len(chunked.chunks),
                    "chunking_config_fingerprint": chunked.config_fingerprint,
                }
            )

        sparse = BM25SparseIndex.build(
            sparse_inputs,
            config=SparseIndexConfig(index_version="phase8_ci_v1"),
        )
        hybrid = HybridRetriever(dense=dense, sparse=sparse)
        financial = next(
            item for item in selected if Path(item.relative_path).name == "financial_report.pdf"
        )
        financial_chunks = chunks_by_document[financial.record.document_id]
        if not financial_chunks:
            raise RuntimeError("financial fixture produced no chunks")
        target = financial_chunks[0]
        entry = next(
            entry
            for entry in sparse.snapshot.entries
            if entry.chunk.chunk_id == target.chunk_id
        )
        unique_terms = sorted(
            term
            for term in set(entry.tokens)
            if sparse.snapshot.document_frequencies.get(term) == 1 and len(term) > 2
        )
        if not unique_terms:
            raise RuntimeError("financial fixture lacks a unique lexical diagnostic term")
        lexical_query = unique_terms[0]
        shared_filter = HybridSearchFilter(
            domain=financial.record.domain,
            document_id=financial.record.document_id,
            chunking_config_fingerprint=target.config_fingerprint,
        )
        lexical = await hybrid.search(lexical_query, top_k=3, filters=shared_filter)
        if not lexical.results or lexical.results[0].chunk.chunk_id != target.chunk_id:
            raise RuntimeError("hybrid lexical query did not recover the expected canonical chunk")

        semantic_query = "revenue performance change across the reporting period"
        semantic_proxy = await hybrid.search(semantic_query, top_k=3, filters=shared_filter)
        if not semantic_proxy.results:
            raise RuntimeError("hybrid natural-language query returned no filtered result")

        expanded_hybrid = HybridRetriever(
            dense=dense,
            sparse=sparse,
            expansion_provider=DictionaryQueryExpansionProvider({"turnover": ["revenue"]}),
            config=HybridRetrievalConfig(
                expansion=QueryExpansionConfig(enabled=True, max_expansions=1)
            ),
        )
        mismatch = await expanded_hybrid.search(
            "quarterly turnover",
            top_k=3,
            filters=shared_filter,
        )
        if mismatch.expansions != ("revenue",):
            raise RuntimeError("deterministic vocabulary expansion was not preserved")
        if not mismatch.results or not any(
            diagnostic.sparse_rank is not None for diagnostic in mismatch.diagnostics
        ):
            raise RuntimeError("expanded vocabulary did not produce sparse lexical evidence")

        concurrent_latencies: list[float] = []
        sequential_latencies: list[float] = []
        for _ in range(3):
            concurrent_latencies.append(
                (await hybrid.search(target.text, top_k=3, filters=shared_filter)).total_latency_ms
            )
            sequential_latencies.append(
                (
                    await hybrid.search_sequential(target.text, top_k=3, filters=shared_filter)
                ).total_latency_ms
            )
        concurrent_median = statistics.median(concurrent_latencies)
        sequential_median = statistics.median(sequential_latencies)

        return {
            "schema_version": "1.0",
            "corpus_fingerprint": manifest.fingerprint,
            "document_count": len(documents),
            "documents": documents,
            "chunk_strategy": chunk_config.strategy.value,
            "indexed_chunk_count": sparse.snapshot.document_count,
            "dense_provider": provider.name,
            "dense_provider_evidence": "local-hash-diagnostic-only",
            "sparse_index_fingerprint": sparse.snapshot.index_fingerprint,
            "hybrid_config_fingerprint": hybrid.config_fingerprint,
            "rrf_k": hybrid.config.rrf_k,
            "branch_top_k": hybrid.config.branch_top_k,
            "queries": {
                "lexical_exact": {
                    "query": lexical_query,
                    "top_chunk_id": lexical.results[0].chunk.chunk_id,
                    "dense_rank": lexical.diagnostics[0].dense_rank,
                    "sparse_rank": lexical.diagnostics[0].sparse_rank,
                    "rrf_score": lexical.results[0].score,
                },
                "semantic_query_proxy": {
                    "query": semantic_query,
                    "top_chunk_id": semantic_proxy.results[0].chunk.chunk_id,
                    "note": (
                        "natural-language dense-path mechanics only; "
                        "local hash is not learned semantic evidence"
                    ),
                },
                "vocabulary_mismatch": {
                    "query": mismatch.query,
                    "retrieval_query": mismatch.retrieval_query,
                    "expansions": list(mismatch.expansions),
                    "top_chunk_id": mismatch.results[0].chunk.chunk_id,
                    "sparse_rank": mismatch.diagnostics[0].sparse_rank,
                },
            },
            "concurrent_vs_sequential": {
                "samples": 3,
                "concurrent_latency_ms": concurrent_latencies,
                "sequential_latency_ms": sequential_latencies,
                "concurrent_median_ms": concurrent_median,
                "sequential_median_ms": sequential_median,
                "observed_speedup_ratio": (
                    sequential_median / concurrent_median if concurrent_median > 0 else None
                ),
                "claim": "observed local fixture timing only; no fixed speedup claim",
            },
        }
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()


def main() -> None:
    print(json.dumps(asyncio.run(build_report()), sort_keys=True))


if __name__ == "__main__":
    main()
