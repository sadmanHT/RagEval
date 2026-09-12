# Implementation State

## Completed

### Phase 1 — Repository foundation, contracts, and quality gates

Merged to `main` and revalidated after merge. The repository has strict shared contracts,
provider protocols/fakes, safe settings/logging, deterministic IDs, typed errors, Qdrant/Redis
Compose infrastructure, canonical verification commands, and GitHub Actions quality/integration
jobs.

### Phase 2 — Corpus contracts, fixtures, data governance, and evaluation split

Implementation validated on branch `phase-02-corpus-contracts` in GitHub Actions run
`34694976109` before final documentation/merge validation.

Implemented scope:
- versioned corpus manifest, split, duplicate, source-locator, and evaluation-binding contracts;
- PDF/DOCX/HTML/HTM discovery without parsing document contents;
- streaming SHA-256 checksums and deterministic document IDs;
- explicit duplicate evidence;
- deterministic corpus and evaluation-dataset fingerprints;
- hard development/evaluation leakage enforcement by checksum and document identity;
- manifest read/write, embedded-fingerprint verification, and source revalidation;
- corpus scan/validate/fingerprint CLI;
- real mixed-format fixtures across financial, legal, and research domains, including an image-only OCR fixture;
- cumulative Phase 1 regression verification.

Implementation validation passed Ruff, Ruff formatting, strict mypy (22 source files), 34 unit
tests, 4 integration tests, package smoke, and the complete 38-test regression suite. Detailed
evidence is in `docs/phases/phase-02-report.md`.

## In progress

### Phase 3 — Document loading, parsing, and OCR

Branch: `phase-03-document-parsing-ocr`.

Scope under validation:
- normalized PDF/DOCX/HTML extraction through project-owned `DocumentElement` contracts;
- page/source coordinates, section hints, headers/footers, lists, captions, and table identity;
- versioned parser configuration plus deterministic parser fingerprints and element IDs;
- explicit OCR fallback behind an injectable adapter, with a local Tesseract implementation;
- single-file and corpus-subset debug JSON CLI without indexing;
- corrupt/unsupported input handling and per-file batch failure collection;
- golden mixed-format fixture tests, dedicated Tesseract CI, and full Phase 1–2 regression checks.

Phase 3 is not complete until the branch and post-merge `main` workflows pass quality, unit,
integration, local OCR, smoke, and cumulative regression gates.

## Later phases

Cleaning, chunking, retrieval, reranking, generation, full evaluation, serving, observability,
deployment hardening, and final release validation remain intentionally deferred to their
respective later phases.
