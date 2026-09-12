from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from qdrant_client import models

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.core.errors import IndexingError
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Chunk, DocumentRecord, Domain, SourceType
from rageval.retrieval.dense import (
    DenseIndexConfig,
    DenseSearchFilter,
    LocalHashDenseEmbeddingProvider,
    QdrantDenseIndex,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"
QDRANT_URL = "http://localhost:6333"


def _record(document_id: str, domain: Domain) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        source_uri=f"fixture://dense/{document_id}",
        source_type=SourceType.PDF,
        domain=domain,
        checksum_sha256=("a" if domain is Domain.FINANCIAL else "b") * 64,
    )


def _chunk(document_id: str, ordinal: int, text: str, *, suffix: str) -> Chunk:
    return Chunk(
        chunk_id=f"chk_{suffix}_{ordinal:04d}",
        document_id=document_id,
        ordinal=ordinal,
        text=text,
        token_count=len(text.split()),
        config_fingerprint="c" * 64,
        metadata={
            "domain": "financial" if "finance" in document_id else "legal",
            "source_pages": [1],
            "source_element_ids": [f"src_{suffix}_{ordinal:04d}"],
        },
    )


async def _fresh_index(name: str, *, dimension: int = 32) -> QdrantDenseIndex:
    provider = LocalHashDenseEmbeddingProvider(dimension=dimension)
    index = QdrantDenseIndex(
        provider=provider,
        config=DenseIndexConfig(
            collection_base="rageval_phase6_test",
            collection_version=name,
            vector_size=dimension,
            exact_search=True,
            timeout_seconds=3.0,
        ),
        url=QDRANT_URL,
    )
    if await index.client.collection_exists(index.config.collection_name):
        await index.client.delete_collection(index.config.collection_name)
    return index


async def _cleanup(index: QdrantDenseIndex) -> None:
    try:
        if await index.client.collection_exists(index.config.collection_name):
            await index.client.delete_collection(index.config.collection_name)
    finally:
        await index.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_upsert_filter_replace_delete_and_idempotency() -> None:
    index = await _fresh_index("lifecycle")
    finance = _record("doc_finance_0001", Domain.FINANCIAL)
    legal = _record("doc_legal_0001", Domain.LEGAL)
    finance_chunks = (
        _chunk(finance.document_id, 0, "revenue growth cash flow quarter", suffix="fin"),
        _chunk(finance.document_id, 1, "operating margin guidance", suffix="fin"),
    )
    legal_chunks = (
        _chunk(legal.document_id, 0, "termination clause governing law", suffix="leg"),
    )

    try:
        await index.upsert_document(finance, finance_chunks, source_date=date(2024, 3, 31))
        await index.upsert_document(legal, legal_chunks, source_date=date(2023, 1, 1))
        await index.upsert_document(finance, finance_chunks, source_date=date(2024, 3, 31))

        count = await index.client.count(index.config.collection_name, exact=True)
        assert count.count == 3
        consistency = await index.check_document_consistency(finance.document_id, finance_chunks)
        assert consistency.consistent is True
        expected_ids = tuple(sorted(chunk.chunk_id for chunk in finance_chunks))
        assert consistency.indexed_chunk_ids == expected_ids

        exact = await index.search(finance_chunks[0].text, top_k=3)
        assert exact.results[0].chunk.chunk_id == finance_chunks[0].chunk_id
        assert exact.results[0].retriever == "dense-qdrant"

        legal_only = await index.search(
            "termination clause",
            top_k=10,
            filters=DenseSearchFilter(domain=Domain.LEGAL),
        )
        assert legal_only.results
        assert all(result.chunk.document_id == legal.document_id for result in legal_only.results)

        recent = await index.search(
            "revenue",
            top_k=10,
            filters=DenseSearchFilter(date_from=date(2024, 1, 1)),
        )
        assert recent.results
        assert all(result.chunk.document_id == finance.document_id for result in recent.results)

        document_only = await index.search(
            "margin",
            top_k=10,
            filters=DenseSearchFilter(document_id=finance.document_id),
        )
        assert {result.chunk.document_id for result in document_only.results} == {
            finance.document_id
        }

        replacement = (
            _chunk(finance.document_id, 0, "updated revenue outlook", suffix="fin_new"),
        )
        mutation = await index.replace_document(
            finance,
            replacement,
            source_date=date(2024, 6, 30),
        )
        assert mutation.operation == "replace"
        replaced = await index.check_document_consistency(finance.document_id, replacement)
        assert replaced.consistent is True
        assert len(replaced.indexed_chunk_ids) == 1

        deleted = await index.delete_document(legal.document_id)
        assert deleted.chunk_count == 1
        legal_after = await index.check_document_consistency(legal.document_id, ())
        assert legal_after.consistent is True
    finally:
        await _cleanup(index)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_rejects_stale_vector_schema() -> None:
    index = await _fresh_index("stale", dimension=8)
    collection_name = index.config.collection_name
    try:
        await index.client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=7, distance=models.Distance.COSINE),
        )
        with pytest.raises(IndexingError, match="Bump collection_version"):
            await index.ensure_collection()
    finally:
        await _cleanup(index)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_unavailable_is_an_explicit_indexing_error() -> None:
    index = QdrantDenseIndex(
        provider=LocalHashDenseEmbeddingProvider(dimension=8),
        config=DenseIndexConfig(
            collection_base="rageval_unreachable",
            collection_version="v1",
            vector_size=8,
            timeout_seconds=0.2,
        ),
        url="http://127.0.0.1:1",
    )
    try:
        with pytest.raises(IndexingError, match="cannot ensure Qdrant collection"):
            await index.ensure_collection()
    finally:
        await index.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fixture_pipeline_retrieves_canonical_chunk_with_provenance() -> None:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    item = next(
        candidate
        for candidate in manifest.documents
        if Path(candidate.relative_path).name == "financial_report.pdf"
    )
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
    )
    cleaned = clean_parsed_document(parsed)
    chunked = await ChunkingEngine().chunk(
        cleaned,
        config=reference_chunking_config(ChunkStrategy.FIXED_512),
    )
    assert chunked.chunks

    index = await _fresh_index("fixture_e2e")
    try:
        await index.upsert_document(
            item.record,
            chunked.chunks,
            source_date=item.source_date,
        )
        response = await index.search(
            chunked.chunks[0].text,
            top_k=1,
            filters=DenseSearchFilter(
                domain=item.record.domain,
                document_id=item.record.document_id,
                chunking_config_fingerprint=chunked.config_fingerprint,
            ),
        )
        assert len(response.results) == 1
        retrieved = response.results[0].chunk
        assert retrieved.chunk_id == chunked.chunks[0].chunk_id
        assert retrieved.config_fingerprint == chunked.config_fingerprint
        assert retrieved.metadata["source_element_ids"] == chunked.chunks[0].metadata[
            "source_element_ids"
        ]
        assert retrieved.metadata["source_pages"] == chunked.chunks[0].metadata["source_pages"]
    finally:
        await _cleanup(index)
