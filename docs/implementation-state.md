# Implementation State

## Completed

### Phase 1 — Repository foundation, contracts, and quality gates

Merged to `main` and revalidated after merge. The repository has strict shared contracts,
provider protocols/fakes, safe settings/logging, deterministic IDs, typed errors, Qdrant/Redis
Compose infrastructure, canonical verification commands, and GitHub Actions quality/integration
jobs.

### Phase 2 — Corpus contracts, fixtures, data governance, and evaluation split

Merged to `main` and revalidated after merge. Phase 2 established versioned corpus/evaluation
contracts, deterministic identities/fingerprints, duplicate/leakage protection, manifest tooling,
and the mixed-format fixture corpus used by later phases. Detailed evidence is in
`docs/phases/phase-02-report.md`.

### Phase 3 — Document loading, parsing, and OCR

Merged to `main` as PR #3 at commit `c898bdd8b91170cf3b371b15620f7203d79ef208` and revalidated
post-merge in GitHub Actions run `34704484873`. Quality, service-backed integration/regression, and
the dedicated installed-Tesseract OCR job all completed successfully on the merge commit.

Implemented scope:
- normalized PDF/DOCX/HTML extraction through project-owned `DocumentElement` contracts;
- page/source coordinates, section hints, headers/footers, lists, captions, page breaks, and table
  identity/HTML where available;
- versioned parser configuration plus deterministic parser fingerprints and element IDs;
- explicit injectable OCR fallback with local Tesseract implementation and OCR provenance;
- single-file and corpus-subset debug JSON CLI without indexing;
- typed corrupt/unsupported input handling and per-file batch failure collection;
- golden mixed-format fixture tests, a dedicated installed-Tesseract CI job, and cumulative
  Phase 1–2 regression verification.

Branch acceptance evidence: Ruff and Ruff formatting passed; strict mypy passed on 25 source files;
42 unit tests passed; regular integration passed 9 tests with the local-OCR-only test intentionally
skipped there; full cumulative regression passed 51 tests with that same one skip; the dedicated
Tesseract job installed the OCR binary and passed the OCR test independently; Qdrant/Redis
readiness, package smoke, and clean Compose teardown all passed. The final evidence head repeated
the three CI gates successfully before merge, and the merge commit repeated them successfully on
`main`. Detailed evidence is in `docs/phases/phase-03-report.md`.

## Next phase

### Phase 4 — Cleaning, normalization, and metadata integrity

Not started. Phase 4 should consume normalized Phase 3 parse output and implement deterministic
cleaning/normalization, repeated header/footer and boilerplate handling, near-duplicate evidence,
and metadata preservation without damaging tables, legal clauses, research references, or source
coordinates. It must retain cumulative Phase 1–3 verification, including the dedicated local-OCR
job.

## Later phases

Chunking, embeddings/dense retrieval, sparse retrieval, fusion/query expansion, reranking/multi-hop,
grounded generation, evaluation, serving, observability/deployment hardening, and final release
validation remain intentionally deferred to their respective later phases.
