from __future__ import annotations

from pathlib import Path

import pytest

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models.contracts import Chunk
from rageval.retrieval.sparse import BM25SparseIndex, SparseDocumentInput, SparseSearchFilter

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"
SELECTED_FIXTURES = {
    "financial_report.pdf",
    "financial_table.pdf",
    "msa.docx",
    "paper.html",
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_phase5_chunks_to_sparse_results_preserve_identity_and_provenance() -> None:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    selected = [
        item for item in manifest.documents if Path(item.relative_path).name in SELECTED_FIXTURES
    ]
    chunk_config = reference_chunking_config(ChunkStrategy.FIXED_512)
    documents: list[SparseDocumentInput] = []
    expected_chunks: dict[str, Chunk] = {}

    for item in selected:
        parsed = parse_corpus_document(
            item,
            FIXTURE_ROOT,
            config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
        )
        cleaned = clean_parsed_document(parsed)
        chunked = await ChunkingEngine().chunk(cleaned, config=chunk_config)
        documents.append(
            SparseDocumentInput(
                document=item.record,
                chunks=chunked.chunks,
                source_date=item.source_date,
            )
        )
        for chunk in chunked.chunks:
            expected_chunks[chunk.chunk_id] = chunk

    index = BM25SparseIndex.build(documents)
    assert index.snapshot.document_count == len(expected_chunks)
    assert index.snapshot.document_count > 0

    for item in selected:
        entries = [
            entry
            for entry in index.snapshot.entries
            if entry.chunk.document_id == item.record.document_id
        ]
        assert entries
        target = entries[0]
        unique_terms = sorted(
            {
                term
                for term in target.tokens
                if index.snapshot.document_frequencies.get(term) == 1 and len(term) > 2
            }
        )
        assert unique_terms, f"fixture {item.relative_path} has no unique lexical term"
        response = await index.search(
            unique_terms[0],
            top_k=1,
            filters=SparseSearchFilter(domain=item.record.domain),
        )
        assert response.results
        result = response.results[0]
        assert result.chunk.chunk_id == target.chunk.chunk_id
        assert result.chunk == expected_chunks[target.chunk.chunk_id]
        assert result.chunk.config_fingerprint == target.chunk.config_fingerprint
        assert result.chunk.metadata.get("source_element_ids")
        assert result.metadata["matched_terms"] == [unique_terms[0]]
        assert result.retriever == "sparse-bm25_plus"
