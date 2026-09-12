"""Emit reproducible Phase 7 BM25/BM25+ fixture evidence."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Domain
from rageval.retrieval.sparse import (
    BM25SparseIndex,
    SparseDocumentInput,
    SparseIndexConfig,
    SparseSearchFilter,
)

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
        (
            item
            for item in manifest.documents
            if Path(item.relative_path).name in SELECTED_FIXTURES
        ),
        key=lambda item: item.relative_path,
    )
    chunk_config = reference_chunking_config(ChunkStrategy.FIXED_512)
    inputs: list[SparseDocumentInput] = []
    document_rows: list[dict[str, object]] = []

    for item in selected:
        parsed = parse_corpus_document(
            item,
            FIXTURE_ROOT,
            config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
        )
        cleaned = clean_parsed_document(parsed)
        chunked = await ChunkingEngine().chunk(cleaned, config=chunk_config)
        inputs.append(
            SparseDocumentInput(
                document=item.record,
                chunks=chunked.chunks,
                source_date=item.source_date,
            )
        )
        document_rows.append(
            {
                "document_id": item.record.document_id,
                "domain": item.record.domain.value,
                "path": item.relative_path,
                "chunk_count": len(chunked.chunks),
                "chunking_config_fingerprint": chunked.config_fingerprint,
            }
        )

    config = SparseIndexConfig(index_version="ci_v1")
    index = BM25SparseIndex.build(inputs, config=config)
    rebuilt = BM25SparseIndex.build(list(reversed(inputs)), config=config)
    if rebuilt.snapshot.index_fingerprint != index.snapshot.index_fingerprint:
        raise RuntimeError("sparse index fingerprint changed when input order changed")

    with tempfile.TemporaryDirectory() as temporary_directory:
        snapshot_path = Path(temporary_directory) / "sparse-index.json"
        index.save(snapshot_path)
        restored = BM25SparseIndex.load(snapshot_path)
        if restored.snapshot.index_fingerprint != index.snapshot.index_fingerprint:
            raise RuntimeError("sparse snapshot round-trip changed index fingerprint")

    queries: list[dict[str, object]] = []
    for item in selected:
        entries = [
            entry
            for entry in index.snapshot.entries
            if entry.chunk.document_id == item.record.document_id
        ]
        if not entries:
            raise RuntimeError(f"no sparse entries for {item.relative_path}")
        target = entries[0]
        unique_terms = sorted(
            {
                term
                for term in target.tokens
                if index.snapshot.document_frequencies.get(term) == 1 and len(term) > 2
            }
        )
        if not unique_terms:
            raise RuntimeError(f"no unique sparse diagnostic term for {item.relative_path}")
        query = unique_terms[0]
        response = await index.search(
            query,
            top_k=1,
            filters=SparseSearchFilter(domain=item.record.domain),
        )
        if not response.results or response.results[0].chunk.chunk_id != target.chunk.chunk_id:
            raise RuntimeError(f"unexpected sparse top result for {item.relative_path}")
        diagnostic = response.diagnostics[0]
        queries.append(
            {
                "document_id": item.record.document_id,
                "domain": item.record.domain.value,
                "query": query,
                "query_tokens": list(response.query_tokens),
                "matched_terms": list(diagnostic.matched_terms),
                "rank": diagnostic.rank,
                "score": diagnostic.score,
                "top_chunk_id": diagnostic.chunk_id,
            }
        )

    domain_counts = {
        domain.value: index.count(SparseSearchFilter(domain=domain)) for domain in Domain
    }
    return {
        "schema_version": "1.0",
        "corpus_fingerprint": manifest.fingerprint,
        "index_version": config.index_version,
        "index_fingerprint": index.snapshot.index_fingerprint,
        "sparse_config_fingerprint": index.snapshot.config_fingerprint,
        "variant": config.variant.value,
        "k1": config.k1,
        "b": config.b,
        "delta": config.delta,
        "default_top_k": config.default_top_k,
        "tokenizer": index.tokenizer.name,
        "chunk_strategy": chunk_config.strategy.value,
        "indexed_chunk_count": index.snapshot.document_count,
        "source_document_count": len(document_rows),
        "average_document_length": index.snapshot.average_document_length,
        "domain_chunk_counts": domain_counts,
        "documents": document_rows,
        "queries": queries,
        "rebuild_deterministic": True,
        "snapshot_round_trip": True,
    }


def main() -> None:
    print(json.dumps(asyncio.run(build_report()), sort_keys=True))


if __name__ == "__main__":
    main()
