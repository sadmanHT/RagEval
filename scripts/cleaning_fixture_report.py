#!/usr/bin/env python3
"""Emit auditable Phase 4 cleaning statistics for the committed fixture corpus."""

from __future__ import annotations

import json
from pathlib import Path

from rageval.cleaning import CleaningConfig, clean_parsed_document
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


def main() -> int:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    rows: list[dict[str, object]] = []
    totals = {
        "documents": 0,
        "elements_in": 0,
        "elements_out": 0,
        "duplicates_removed": 0,
        "boilerplate_removed": 0,
        "ocr_elements": 0,
        "tables_preserved": 0,
        "characters_in": 0,
        "characters_out": 0,
        "characters_removed": 0,
    }

    for item in sorted(manifest.documents, key=lambda entry: entry.relative_path):
        name = Path(item.relative_path).name
        parsed = parse_corpus_document(
            item,
            FIXTURE_ROOT,
            config=_parser_config(name),
            ocr_adapter=FixtureOCR() if name == "scanned_notice.pdf" else None,
        )
        cleaned = clean_parsed_document(parsed, config=CleaningConfig())
        stats = cleaned.stats.model_dump(mode="json")
        row = {
            "path": item.relative_path,
            "domain": item.record.domain.value,
            "stats": stats,
        }
        rows.append(row)
        totals["documents"] += 1
        for key in totals:
            if key != "documents":
                totals[key] += int(stats[key])

    if totals["elements_out"] > totals["elements_in"]:
        raise RuntimeError("cleaning unexpectedly increased element count")
    if totals["characters_out"] > totals["characters_in"]:
        raise RuntimeError("cleaning unexpectedly increased character count")

    print(json.dumps({"documents": rows, "totals": totals}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
