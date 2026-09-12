#!/usr/bin/env python3
"""Emit machine-readable Phase 5 chunking ablation statistics for committed fixtures."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rageval.chunking import (
    ChunkStrategy,
    LocalHashEmbeddingProvider,
    reference_chunking_config,
    run_chunking_ablation,
)
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig

FIXTURE_ROOT = Path(__file__).parents[1] / "tests" / "fixtures" / "corpus"


class FixtureOCR:
    """Deterministic OCR adapter for the image-only legal fixture."""

    @property
    def name(self) -> str:
        return "fixture-ocr"

    def extract_page_text(self, path: Path, page_number: int, *, dpi: int) -> str:
        if path.name != "scanned_notice.pdf" or page_number != 1 or dpi < 72:
            raise ValueError("unexpected OCR fixture request")
        return "Scanned legal notice requires OCR fallback."


def _parser_config(name: str) -> ParserConfig:
    if name == "scanned_notice.pdf":
        return ParserConfig(ocr_mode=OCRMode.FALLBACK, ocr_min_native_chars=20)
    return ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True)


async def _run() -> int:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    documents = []
    for item in sorted(manifest.documents, key=lambda entry: entry.relative_path):
        name = Path(item.relative_path).name
        parsed = parse_corpus_document(
            item,
            FIXTURE_ROOT,
            config=_parser_config(name),
            ocr_adapter=FixtureOCR() if name == "scanned_notice.pdf" else None,
        )
        documents.append(clean_parsed_document(parsed))

    configs = tuple(reference_chunking_config(strategy) for strategy in ChunkStrategy)
    report = await run_chunking_ablation(
        documents,
        configs=configs,
        embedding_provider=LocalHashEmbeddingProvider(),
        metadata={
            "dataset": "committed-phase2-3-fixture-corpus",
            "semantic_embedding_evidence": "local-hash-diagnostic-only",
        },
    )

    if {stat.strategy for stat in report.stats} != set(ChunkStrategy):
        raise RuntimeError("not every reference chunking strategy produced statistics")
    if any(stat.provenance_coverage != 1.0 for stat in report.stats):
        raise RuntimeError("chunking lost source-element provenance coverage")
    if any(stat.table_fragmentation_count != 0 for stat in report.stats):
        raise RuntimeError("table-aware fixture chunking fragmented a table incorrectly")

    print(json.dumps(report.model_dump(mode="json"), sort_keys=True, default=str))
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
