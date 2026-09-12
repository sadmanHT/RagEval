"""Emit reproducible Phase 6 dense-index fixture evidence from a real local Qdrant."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rageval.chunking import ChunkingEngine, ChunkStrategy, reference_chunking_config
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Domain
from rageval.retrieval.dense import (
    DenseIndexConfig,
    DenseSearchFilter,
    LocalHashDenseEmbeddingProvider,
    QdrantDenseIndex,
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
    selected = [
        item
        for item in manifest.documents
        if Path(item.relative_path).name in SELECTED_FIXTURES
    ]
    chunk_config = reference_chunking_config(ChunkStrategy.FIXED_512)
    provider = LocalHashDenseEmbeddingProvider(dimension=64)
    index = QdrantDenseIndex(
        provider=provider,
        config=DenseIndexConfig(
            collection_base="rageval_phase6_fixture",
            collection_version="ci_v1",
            vector_size=provider.dimension,
            exact_search=True,
        ),
    )
    collection_name = index.config.collection_name
    documents: list[dict[str, object]] = []
    queries: list[dict[str, object]] = []
    try:
        if await index.client.collection_exists(collection_name):
            await index.client.delete_collection(collection_name)
        await index.ensure_collection()

        for item in selected:
            parsed = parse_corpus_document(
                item,
                FIXTURE_ROOT,
                config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
            )
            cleaned = clean_parsed_document(parsed)
            chunked = await ChunkingEngine().chunk(cleaned, config=chunk_config)
            await index.upsert_document(
                item.record,
                chunked.chunks,
                source_date=item.source_date,
            )
            consistency = await index.check_document_consistency(
                item.record.document_id,
                chunked.chunks,
            )
            if not consistency.consistent:
                raise RuntimeError(f"inconsistent fixture index for {item.relative_path}")
            documents.append(
                {
                    "document_id": item.record.document_id,
                    "domain": item.record.domain.value,
                    "path": item.relative_path,
                    "chunk_count": len(chunked.chunks),
                    "chunking_config_fingerprint": chunked.config_fingerprint,
                }
            )
            if chunked.chunks:
                response = await index.search(
                    chunked.chunks[0].text,
                    top_k=1,
                    filters=DenseSearchFilter(
                        domain=item.record.domain,
                        document_id=item.record.document_id,
                        chunking_config_fingerprint=chunked.config_fingerprint,
                    ),
                )
                if not response.results:
                    raise RuntimeError(f"no dense result for {item.relative_path}")
                if response.results[0].chunk.chunk_id != chunked.chunks[0].chunk_id:
                    raise RuntimeError(f"unexpected top dense result for {item.relative_path}")
                queries.append(
                    {
                        "document_id": item.record.document_id,
                        "domain": item.record.domain.value,
                        "top_chunk_id": response.results[0].chunk.chunk_id,
                        "score": response.results[0].score,
                        "embedding_latency_ms": response.embedding_latency_ms,
                        "qdrant_latency_ms": response.qdrant_latency_ms,
                        "total_latency_ms": response.total_latency_ms,
                    }
                )

        count = await index.client.count(collection_name, exact=True)
        domain_counts: dict[str, int] = {}
        for domain in Domain:
            response = await index.search(
                "fixture domain check",
                top_k=100,
                filters=DenseSearchFilter(domain=domain),
            )
            if any(result.chunk.metadata.get("domain") != domain.value for result in response.results):
                raise RuntimeError(f"domain filter leaked results for {domain.value}")
            domain_counts[domain.value] = len(response.results)

        return {
            "schema_version": "1.0",
            "corpus_fingerprint": manifest.fingerprint,
            "collection": collection_name,
            "embedding_provider": provider.name,
            "embedding_model": provider.model,
            "embedding_dimension": provider.dimension,
            "embedding_evidence": "local-hash-diagnostic-only",
            "chunk_strategy": chunk_config.strategy.value,
            "indexed_point_count": count.count,
            "document_count": len(documents),
            "documents": documents,
            "domain_result_counts": domain_counts,
            "queries": queries,
        }
    finally:
        try:
            if await index.client.collection_exists(collection_name):
                await index.client.delete_collection(collection_name)
        finally:
            await index.aclose()


def main() -> None:
    report = asyncio.run(build_report())
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
