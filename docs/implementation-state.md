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

## Next phase

### Phase 3 — Document loading, parsing, and OCR

Phase 3 should consume the Phase 2 manifest/source contracts and implement normalized PDF, DOCX,
and HTML extraction with provenance preservation and explicit OCR fallback. The committed
image-only legal PDF must be used to prove the OCR branch is genuinely exercised.

Cleaning, chunking, retrieval, reranking, generation, full evaluation, serving, observability,
deployment hardening, and final release validation remain intentionally deferred to their
respective later phases.
