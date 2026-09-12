# Phase 4 — Cleaning, Normalization, Deduplication & Metadata Integrity

## Mission

Transform Phase 3 `ParsedDocument` / `DocumentElement` output into deterministic retrieval-ready
content without destroying financial table structure, legal clause references, research
section/equation/citation syntax, or source provenance needed for answer citations and debugging.

## Boundary

Phase 4 consumes project-owned Phase 3 contracts. It does not reach back into PyMuPDF,
python-docx, BeautifulSoup, or OCR library objects. The cleaning boundary emits project-owned
`CleanedDocument` data with retained `DocumentElement` instances, removal evidence, cleaning
statistics, and a deterministic cleaning configuration fingerprint.

## Required behavior

- Normalize Unicode, parser control artifacts, zero-width/soft-hyphen artifacts, whitespace, line
  endings, and word hyphenation across line breaks while retaining meaningful punctuation and
  numeric formatting.
- Preserve table row and cell separators and all parser-provided structured table metadata,
  including `table_html`, source offsets, page number, and bounding boxes.
- Suppress repeated headers, footers, and page-number elements only after repeated-pattern evidence;
  do not perform blind line deletion.
- Detect exact/near duplicate boilerplate with a configurable threshold, cross-page evidence, and a
  conservative eligibility signal. Keep the first representative and record typed evidence for
  each removal.
- Never classify arbitrary repeated body text as boilerplate solely because it repeats.
- Preserve legal clause numbering, ticker/currency/percentage syntax, research section/equation/
  citation references, and all original source metadata on retained elements.
- Generate deterministic cleaned element IDs tied to the source element ID, normalized text,
  element type, and cleaning configuration fingerprint.
- Record per-document statistics for elements in/out, duplicate removals, boilerplate removals,
  repeated header/footer/page-number removals, OCR elements, tables preserved, and characters
  in/out/removed.

## Deterministic evidence strategy

Two complementary fixture sets are required:

1. **Inherited preservation corpus** — the five Phase 2/3 raw fixtures are parsed through the real
   Phase 3 loaders and cleaned. Because these fixtures were designed to be compact and already
   clean, Phase 4 must not invent reductions. They establish that answer-bearing content, OCR
   output, table structure, and provenance survive unchanged when no cleaning is warranted.
2. **Noisy Phase 4 golden fixtures** — financial, legal, and research parsed-element fixtures
   intentionally contain repeated page artifacts, duplicate boilerplate, whitespace/control/
   hyphenation noise, structured tables, clause numbers, and research references. Their aggregate
   element and character counts must both decrease while all expected answer-bearing content and
   metadata remain present.

The CI statistics step emits actual per-fixture and aggregate values. Those generated values are
what the phase report records; documentation constants are not substitutes for a run.

## Verification gate

The phase is not complete until the final PR head passes:

```bash
ruff check .
ruff format --check .
mypy src
pytest -q tests/unit

docker compose config
docker compose up -d qdrant redis
python scripts/wait_for_services.py
pytest -q tests/integration
python scripts/cleaning_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v

# separate local OCR job with Tesseract installed
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

After merge, the merge commit must pass the same quality, integration/regression/statistics, and
installed-Tesseract jobs on `main`. Repository status documentation is only marked complete after
that post-merge evidence is green.

## Phase 5 handoff

Phase 5 chunking must consume cleaned elements rather than reparsing/recleaning source files. It
must preserve Phase 4 `source_element_id` provenance and table boundaries while implementing
controlled fixed-token 256/512/1024 and semantic chunking strategies suitable for per-domain
ablation. No preferred chunk size may be claimed without measured evaluation evidence.
