# Phase 4 Completion Report

## Status

Complete. Phase 4 merged to `main` as PR #4 at merge commit
`4366bb0f5a5a7a4f7184eb24fdf744d9eddfb502` after the final PR head passed all quality,
integration/regression/statistics, and installed-Tesseract OCR gates. The merge commit then repeated
all three jobs successfully on `main` in GitHub Actions run `34705921835`.

Validated implementation/evidence head:
`097d9a27b335bf125a688c90ca10be42cb7f2c00`.

Implementation acceptance run: `34705690248`.
Final PR documentation head: `663c7881cdedab9388f41defe692c4c2e517b954`.
Final PR-head CI run: `34705879334`.
Post-merge `main` CI run: `34705921835`.

## Implemented scope

Phase 4 adds a deterministic cleaning layer between Phase 3 parsing and future chunking. The
cleaner consumes project-owned `ParsedDocument` / `DocumentElement` contracts and produces a
`CleanedDocument` with retained normalized elements, typed removal evidence, cleaning statistics,
and a deterministic cleaning configuration fingerprint.

Implemented behavior:

- Unicode NFC/NFKC normalization, line-ending normalization, control/zero-width/soft-hyphen
  removal, whitespace normalization, and line-wrap dehyphenation;
- preservation of semantically significant punctuation and numeric syntax, including currencies,
  percentages, ticker symbols, legal clause labels, equation references, and research citations;
- repeated header/footer/page-number suppression only after cross-page pattern evidence;
- configurable near-duplicate boilerplate clustering with a deterministic similarity threshold;
- conservative boilerplate eligibility based on an explicit parser/fixture signal or configured
  boilerplate markers, so arbitrary repeated body text is not deleted merely because it repeats;
- retention of the first boilerplate representative and typed audit evidence for later removals;
- table-preserving normalization that retains row/newline and cell/tab relationships together with
  parser-provided `table_html`, bounding boxes, source offsets, page numbers, and section metadata;
- deterministic cleaned element IDs plus `source_element_id` links back to the Phase 3 element;
- propagation of source parser/configuration provenance through every retained element;
- per-document cleaning statistics for elements, duplicate/boilerplate removals, headers/footers,
  page numbers, OCR elements, tables, and character counts;
- a deterministic fixture-statistics command permanently wired into CI.

## Files and boundaries

Primary production files:

- `src/rageval/cleaning/models.py`
- `src/rageval/cleaning/normalizer.py`
- `src/rageval/cleaning/cleaner.py`
- `src/rageval/cleaning/__init__.py`

Verification/evidence additions:

- `tests/unit/test_cleaning.py`
- `tests/unit/test_cleaning_goldens.py`
- `tests/integration/test_cleaning_fixtures.py`
- `tests/fixtures/cleaning/golden_cases.json`
- `scripts/cleaning_fixture_report.py`
- `.github/workflows/ci.yml`

No PDF, DOCX, HTML, OCR, or other third-party parser object crosses into the cleaning layer. Phase 4
only consumes the normalized project contracts established in Phase 3.

## Architecture decisions

### Cleaning is a provenance-preserving transform

A cleaned element receives a deterministic ID derived from the source element ID, normalized text,
element type, and cleaning configuration fingerprint. The original Phase 3 element ID is retained
as `source_element_id`, and all original metadata is copied forward before cleaning metadata is
added. This makes cleaned IDs configuration-sensitive without sacrificing backwards traceability.

### Repeated page artifacts require structural evidence

General header/footer suppression only evaluates elements already classified as `HEADER` or
`FOOTER` and requires the canonicalized pattern to occur across the configured number of pages.
Page-varying numbers are canonicalized for repeated-pattern detection. This avoids blind line
removal from arbitrary body content.

### Near-duplicate removal is intentionally conservative

Similarity alone is not sufficient evidence that repeated content is boilerplate. Candidate body
text must also carry `boilerplate_candidate=true` or contain one of the configured boilerplate
markers. Clusters must span multiple pages. The first representative is retained; later matches are
removed with the matched source element ID and similarity recorded. Legitimate repeated legal body
text is covered by a golden test and remains present.

### Tables remain structured

Table text normalization preserves newline-delimited rows and tab-delimited cells. Structured
metadata emitted by Phase 3 (`table_html`, `bbox`, `source_offset`, page number, section hints) is
retained verbatim. Phase 4 does not attempt semantic table reconstruction; that responsibility is
outside this phase.

### Preservation and reduction evidence are separate

The inherited Phase 2/3 corpus fixtures are compact and already clean. Their Phase 4 run therefore
acts as a preservation test, not a reduction benchmark. Separate noisy Phase 4 golden fixtures were
added for financial, legal, and research documents so the completion gate can demonstrate actual
noise removal without inventing reductions in the inherited corpus.

## Verification evidence

Implementation acceptance run `34705690248`, final PR-head run `34705879334`, and post-merge
`main` run `34705921835` all completed the relevant three CI jobs successfully.

Quality evidence on the accepted implementation:

- `ruff check .` — passed;
- `ruff format --check .` — passed, 67 files already formatted;
- `mypy src` — passed, no issues in 29 source files;
- `pytest -q tests/unit` — 53 passed.

Integration/regression evidence:

- `docker compose config` — passed;
- Qdrant and Redis start/readiness — passed;
- `pytest -q tests/integration` — 14 passed, 1 skipped;
- the sole integration skip is the explicitly local-OCR-only test because this runner does not
  install Tesseract;
- `python scripts/cleaning_fixture_report.py` — passed;
- `python -m rageval.smoke` — passed;
- `pytest -q` — 67 passed, 1 skipped (the same local-OCR-only test);
- Compose teardown with volumes — passed.

Dedicated local-OCR evidence:

- installed Tesseract 5.3.4 from Ubuntu packages;
- `pytest -q -m local_ocr tests/integration/test_local_ocr.py` — 1 passed.

No hosted-provider credentials are relevant to Phase 4. No OpenAI, Cohere, Anthropic, Langfuse, or
W&B result is claimed.

## Cleaning statistics produced by CI

The statistics below were emitted by `scripts/cleaning_fixture_report.py` in acceptance run
`34705690248`; they are run results, not documentation constants.

### Inherited preservation corpus

Five Phase 2/3 fixtures remained unchanged because no cleaning action was warranted:

- documents: 5;
- elements: 13 in -> 13 out;
- characters: 719 in -> 719 out;
- characters removed: 0;
- duplicate removals: 0;
- boilerplate removals: 0;
- OCR elements observed: 1;
- tables preserved: 1.

Per fixture:

- `financial_report.pdf`: 3 -> 3 elements, 142 -> 142 characters;
- `msa.docx`: 4 -> 4 elements, 281 -> 281 characters;
- `financial_table.pdf`: 2 -> 2 elements, 114 -> 114 characters, 1 table preserved;
- `scanned_notice.pdf`: 1 -> 1 element, 43 -> 43 characters, 1 OCR element;
- `paper.html`: 3 -> 3 elements, 139 -> 139 characters.

This is intentionally reported as preservation evidence, not as a cleaning reduction.

### Noisy Phase 4 golden corpus

The three purpose-built noisy domain fixtures produced actual reductions while retaining all
answer-bearing assertions:

- financial: 12 -> 4 elements; 409 -> 173 characters; 236 characters removed; 2 duplicate
  removals; 8 boilerplate/page-artifact removals; 1 table preserved;
- legal: 13 -> 5 elements; 431 -> 259 characters; 172 characters removed; 2 duplicate removals;
  8 boilerplate/page-artifact removals; repeated legitimate Section 7.4 body text retained twice;
- research: 12 -> 4 elements; 399 -> 204 characters; 195 characters removed; 2 duplicate removals;
  8 boilerplate/page-artifact removals.

Aggregate noisy-golden result:

- documents: 3;
- elements: **37 -> 13**;
- characters: **1,239 -> 636**;
- characters removed: **603**;
- duplicate removals: **6**;
- boilerplate/page-artifact removals: **24**;
- tables preserved: **1**.

The goldens assert survival of currency/percentage formatting, ticker syntax, clause labels,
research equation/citation references, table coordinates/HTML/source offsets, section hints, and
direct source-element traceability.

## Evidence refinement during implementation

The first implementation head passed the quality, integration/regression, and local-OCR jobs. The
first statistics run then showed that the inherited fixture corpus was already clean: 13 -> 13
elements and 719 -> 719 characters. Rather than claim a fabricated reduction, Phase 4 added noisy
financial/legal/research golden fixtures plus fail-closed CI assertions requiring those fixtures to
reduce both element and character counts and exercise boilerplate deduplication. The resulting
implementation/evidence head `097d9a27...` passed the complete suite above.

No tests, assertions, lint rules, type-check settings, or previous-phase gates were weakened.

## Known limitations

- The repository does not contain the target production-scale ~12,000-document corpus, so no
  production-corpus cleaning percentages are claimed.
- Boilerplate markers, length bounds, repeat-page counts, and similarity thresholds are
  configuration heuristics. Later evaluation/ablation work should tune them from evidence rather
  than treating the defaults as universally optimal.
- Near-duplicate similarity is intentionally conservative token-set Jaccard, not semantic
  similarity. This reduces the risk of deleting answer-bearing paraphrases but may leave some
  semantically redundant boilerplate.
- General repeated-pattern suppression depends on Phase 3 `HEADER`/`FOOTER` classification. Body
  text is not silently reclassified as a page artifact.
- Table structure is retained from the parser representation and metadata; Phase 4 does not infer
  missing semantic row/column relationships that the source parser did not extract.
- GitHub Actions currently emits a Node 20 deprecation warning for the pinned checkout/setup-python
  action versions. The warning is external to Phase 4 and does not fail the test gates.

## Phase 5 handoff

Phase 5 chunking must consume `CleanedDocument.elements`; it must not reparse or independently
reclean source files. Chunking must preserve Phase 4 `source_element_id` provenance and table
boundaries while implementing controlled fixed-token 256/512/1024 and semantic chunking
strategies. The preferred strategy and any per-domain differences must be established by measured
ablation evidence rather than copied from the reference document.
