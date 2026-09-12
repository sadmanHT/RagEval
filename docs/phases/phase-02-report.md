# Phase 2 Completion Report

## Scope

Phase 2 establishes the corpus/data-governance boundary that all later ingestion, retrieval, and evaluation work will consume. It defines what files belong to the corpus, how source identity and provenance are represented, how development and held-out evaluation data are separated, and how a corpus revision is fingerprinted without parsing document contents.

The implementation follows the Phase 2 rule that corpus quality and leakage protection must exist before document parsing begins. It does not fabricate the target 12,000-document corpus or the target 200-question evaluation set; those remain project targets until real reviewed data is supplied.

## Repository state

- Repository: `sadmanHT/RagEval`
- Development branch: `phase-02-corpus-contracts`
- Pull request: #2
- Successful implementation validation commit: `87e60fa2410fc853b61e0de84045e4cf52521493`
- Successful GitHub Actions run: `34694976109`
- CI runner Python: 3.11.16
- Phase 1 base: `ea57d3cdbf60450a2357eeecdca3c309c96ef6f6`

## Major files and components added

- `src/rageval/corpus/models.py` — immutable/versioned corpus, split, locator, duplicate, manifest, and evaluation-binding contracts.
- `src/rageval/corpus/manifest.py` — recursive source discovery, streaming SHA-256, duplicate grouping, deterministic corpus fingerprinting, leakage enforcement, manifest read/write, and source-file revalidation.
- `src/rageval/corpus/cli.py` — `scan`, `validate`, and `fingerprint` commands.
- `scripts/corpus_manifest.py` — executable convenience wrapper for the corpus CLI.
- `src/rageval/evaluation/dataset.py` — deterministic evaluation-record fingerprinting.
- `src/rageval/core/errors.py` — adds `DataLeakageError` as a typed validation failure.
- `tests/unit/test_corpus_manifest.py` — fingerprint, duplicates, leakage, unsupported input, layout, tamper, and missing-file cases.
- `tests/unit/test_corpus_models.py` — governance metadata and source-coordinate validation.
- `tests/unit/test_corpus_cli.py` — CLI scan/validate/fingerprint and failure behavior.
- `tests/unit/test_evaluation_dataset.py` — evaluation split and fingerprint tests.
- `tests/integration/test_corpus_fixtures.py` — real mixed-format fixture discovery/round-trip validation.
- `tests/fixtures/corpus/` — five deterministic PDF/DOCX/HTML fixtures across all three domains and both data splits.
- `docs/plans/phase-02-corpus-data.md` — implemented Phase 2 contract and acceptance gate.

## Data-governance decisions

1. Corpus layout is explicit: `<root>/<development|evaluation>/<financial|legal|research>/<file>`. Split and domain are therefore governance inputs, not content-classification guesses.
2. Phase 2 discovers PDF, DOCX, HTML, and HTM files without parsing their document contents. Parsing/OCR begins in Phase 3.
3. Every source is streamed through SHA-256; large files do not need to be loaded completely into memory to calculate identity.
4. Document IDs reuse the Phase 1 deterministic ID helper and are derived from checksum plus source URI.
5. Renaming a byte-identical source cannot bypass held-out isolation: leakage is checked by both document ID and checksum.
6. Same-split byte-identical files are not silently discarded. They are surfaced as `DuplicateGroup` evidence so later ingestion policy can make an explicit deduplication decision.
7. Unsupported extensions are reported by default and can be made fatal with `--fail-on-unsupported` / `fail_on_unsupported=True`.
8. Corpus fingerprints are independent of discovery ordering and scan timestamps. Audit timestamps remain in manifest records, while the fingerprint represents stable corpus/config identity.
9. Manifest loading recomputes and verifies the embedded fingerprint. Source validation also rechecks file existence and checksum and rejects paths escaping the configured corpus root.
10. `EvaluationDatasetRecord` can only use the held-out evaluation split and binds examples to supporting document IDs plus a corpus fingerprint.

## Fixture corpus

The committed miniature corpus contains five real container/file formats:

- development / financial: text PDF (`financial_report.pdf`)
- development / legal: DOCX agreement (`msa.docx`)
- evaluation / financial: table-oriented PDF (`financial_table.pdf`)
- evaluation / legal: image-only scanned PDF (`scanned_notice.pdf`)
- evaluation / research: HTML research note (`paper.html`)

The PDF/DOCX fixtures were rendered and visually inspected before commit. The scanned legal fixture is intentionally image-only; local `pdftotext` extraction produced no meaningful text, so Phase 3 has a genuine OCR-path fixture rather than a text PDF merely named “scanned.” The DOCX was also opened successfully with `python-docx` during fixture QA.

## Verification evidence

GitHub Actions run `34694976109` completed both jobs successfully against the implementation head.

### Quality job

- `ruff check .` — passed.
- `ruff format --check .` — passed; 43 files already formatted.
- `mypy src` — passed; no issues in 22 source files.
- `pytest -q tests/unit` — 34 passed in 0.70s.

### Integration and cumulative regression job

- `docker compose config` — passed.
- `docker compose up -d qdrant redis` — passed.
- Service readiness probe — Qdrant and Redis ready.
- `pytest -q tests/integration` — 4 passed in 0.09s, including Phase 2 fixture scanning plus Phase 1 service checks.
- `python -m rageval.smoke` — `rageval smoke: ok (development)`.
- `pytest -q` — 38 passed in 0.16s.
- `docker compose down -v` — clean teardown passed.

## Defects found by the gate and fixed

Phase 2 was deliberately not accepted on the first implementation commit. CI found and drove fixes for:

1. a Ruff line-length violation in the manifest checksum-mismatch error;
2. a Ruff import-formatting violation in the fixture integration test;
3. a second import-block normalization issue that remained after the first style fix.

Each issue was fixed in source and a complete PR workflow was triggered again. No lint rule, type check, assertion, fixture, or service-backed test was weakened to force success. Earlier failing heads still passed the integration/full-regression job, demonstrating that the final acceptance failure was genuinely the quality gate rather than hidden application breakage.

## External/live validation

No OpenAI, Cohere, Anthropic, Langfuse, W&B, GPU, or production-corpus validation is required for Phase 2. No such check is being represented as passed. The repository currently validates deterministic corpus governance and local infrastructure only.

## Known limitations and Phase 3 handoff

Phase 2 records parser version as `unparsed` because it intentionally does not extract document content. Phase 3 must consume these manifest/source contracts and implement PDF/DOCX/HTML loaders, normalized document elements, page/source provenance, explicit OCR fallback, corrupt-file handling, and parser-version metadata.

The five committed fixtures are the required starting acceptance set for Phase 3. In particular, the image-only legal PDF must exercise the OCR path rather than being treated as an ordinary text PDF.
