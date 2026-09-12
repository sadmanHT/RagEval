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
from rageval.retrieval.hybrid import (
    DictionaryQueryExpansionProvider,
    HybridRetrievalConfig,
    HybridRetriever,
    HybridSearchFilter,
    QueryExpansionConfig,
)
from rageval.retrieval.sparse import BM25SparseIndex, SparseDocumentInput, SparseIndexConfig

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "corpus"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_qdrant_and_bm25_fuse_same_canonical_chunks_with_provenance() -> None:
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
            collection_base="rageval_phase8_integration",
            collection_version="test_v1",
            vector_size=provider.dimension,
            exact_search=True,
        ),
    )
    sparse_inputs: list[SparseDocumentInput] = []
    chunked_by_document: dict[str, tuple[object, ...]] = {}
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
            chunked_by_document[item.record.document_id] = tuple(chunked.chunks)
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
            config=SparseIndexConfig(index_version="phase8_test_v1"),
        )
        hybrid = HybridRetriever(dense=dense, sparse=sparse)

        for item in selected:
            chunks = chunked_by_document[item.record.document_id]
            assert chunks
            target = chunks[0]
            response = await hybrid.search(
                target.text,
                top_k=3,
                filters=HybridSearchFilter(
                    domain=item.record.domain,
                    document_id=item.record.document_id,
                    chunking_config_fingerprint=target.config_fingerprint,
                ),
            )
            assert response.results
            assert response.results[0].chunk == target
            assert response.results[0].chunk.document_id == item.record.document_id
            assert response.results[0].chunk.metadata.get("source_element_ids")
            assert response.diagnostics[0].dense_rank == 1
            assert response.diagnostics[0].sparse_rank is not None
            assert response.results[0].metadata["hybrid_config_fingerprint"] == (
                response.config_fingerprint
            )

        financial = next(
            item for item in selected if Path(item.relative_path).name == "financial_report.pdf"
        )
        expanded = HybridRetriever(
            dense=dense,
            sparse=sparse,
            expansion_provider=DictionaryQueryExpansionProvider({"turnover": ["revenue"]}),
            config=HybridRetrievalConfig(
                expansion=QueryExpansionConfig(enabled=True, max_expansions=1)
            ),
        )
        mismatch = await expanded.search(
            "quarterly turnover",
            filters=HybridSearchFilter(
                domain=financial.record.domain,
                document_id=financial.record.document_id,
            ),
        )
        assert mismatch.expansions == ("revenue",)
        assert "quarterly turnover" in mismatch.retrieval_query
        assert mismatch.results
        assert any(diagnostic.sparse_rank is not None for diagnostic in mismatch.diagnostics)
    finally:
        try:
            if await dense.client.collection_exists(collection_name):
                await dense.client.delete_collection(collection_name)
        finally:
            await dense.aclose()
