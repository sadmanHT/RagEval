#!/usr/bin/env python3
"""Emit auditable Phase 4 cleaning statistics for baseline and noisy golden fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from rageval.cleaning import CleaningConfig, clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParsedDocument, ParserConfig
from rageval.models import DocumentElement, DocumentRecord, Domain, ElementType, SourceType

REPO_ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "corpus"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "cleaning" / "golden_cases.json"
STAT_KEYS = (
    "elements_in",
    "elements_out",
    "duplicates_removed",
    "boilerplate_removed",
    "ocr_elements",
    "tables_preserved",
    "characters_in",
    "characters_out",
    "characters_removed",
)


class FixtureOCR:
    """Deterministic OCR adapter for the image-only legal fixture."""

    @property
    def name(self) -> str:
        return "fixture-ocr"

    def extract_page_text(self, path: Path, page_number: int, *, dpi: int) -> str:
        if path.name != "scanned_notice.pdf" or page_number != 1 or dpi < 72:
            raise ValueError("unexpected OCR fixture request")
        return "Scanned legal notice requires OCR fallback."


def _empty_totals() -> dict[str, int]:
    return {"documents": 0, **dict.fromkeys(STAT_KEYS, 0)}


def _add_stats(totals: dict[str, int], stats: dict[str, object]) -> None:
    totals["documents"] += 1
    for key in STAT_KEYS:
        totals[key] += int(stats[key])


def _parser_config(name: str) -> ParserConfig:
    if name == "scanned_notice.pdf":
        return ParserConfig(ocr_mode=OCRMode.FALLBACK, ocr_min_native_chars=20)
    return ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True)


def _baseline_report() -> dict[str, object]:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    rows: list[dict[str, object]] = []
    totals = _empty_totals()
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
        rows.append(
            {
                "path": item.relative_path,
                "domain": item.record.domain.value,
                "stats": stats,
            }
        )
        _add_stats(totals, stats)
    return {"documents": rows, "totals": totals}


def _golden_parsed(case: dict[str, object]) -> ParsedDocument:
    name = str(case["name"])
    raw_elements = case["elements"]
    if not isinstance(raw_elements, list):
        raise TypeError("golden fixture elements must be a list")
    elements = tuple(
        DocumentElement(
            element_id=str(raw["element_id"]),
            document_id=f"doc_{name}_fixture",
            kind=ElementType(str(raw["kind"])),
            text=str(raw["text"]),
            page_number=int(raw["page_number"]) if raw["page_number"] is not None else None,
            metadata=dict(raw["metadata"]),
        )
        for raw in raw_elements
        if isinstance(raw, dict)
    )
    return ParsedDocument(
        document=DocumentRecord(
            document_id=f"doc_{name}_fixture",
            source_uri=f"fixture://cleaning/{name}",
            source_type=SourceType(str(case["source_type"])),
            domain=Domain(str(case["domain"])),
            checksum_sha256="c" * 64,
        ),
        parser_name="phase4-golden-fixture",
        parser_version="1.0",
        config_fingerprint="d" * 64,
        elements=elements,
        used_ocr=False,
    )


def _golden_report() -> dict[str, object]:
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise TypeError("golden fixture root must be a list")
    rows: list[dict[str, object]] = []
    totals = _empty_totals()
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise TypeError("golden fixture entries must be objects")
        case = dict(raw_case)
        parsed = _golden_parsed(case)
        cleaned = clean_parsed_document(parsed, config=CleaningConfig())
        stats = cleaned.stats.model_dump(mode="json")
        rows.append({"name": case["name"], "domain": case["domain"], "stats": stats})
        _add_stats(totals, stats)

    if totals["elements_out"] >= totals["elements_in"]:
        raise RuntimeError("noisy golden fixtures did not reduce element count")
    if totals["characters_out"] >= totals["characters_in"]:
        raise RuntimeError("noisy golden fixtures did not reduce character count")
    if totals["duplicates_removed"] == 0 or totals["boilerplate_removed"] == 0:
        raise RuntimeError("noisy golden fixtures did not exercise boilerplate deduplication")
    return {"documents": rows, "totals": totals}


def main() -> int:
    baseline = _baseline_report()
    baseline_totals = baseline["totals"]
    assert isinstance(baseline_totals, dict)
    if baseline_totals["elements_out"] > baseline_totals["elements_in"]:
        raise RuntimeError("cleaning unexpectedly increased baseline element count")
    if baseline_totals["characters_out"] > baseline_totals["characters_in"]:
        raise RuntimeError("cleaning unexpectedly increased baseline character count")

    report = {
        "baseline_preservation_corpus": baseline,
        "noisy_cleaning_goldens": _golden_report(),
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
