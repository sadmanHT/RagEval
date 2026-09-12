# Implementation State

## Completed

### Phase 1 — Repository foundation, contracts, and quality gates

Merged to `main` and revalidated after merge. The repository has strict shared contracts,
provider protocols/fakes, safe settings/logging, deterministic IDs, typed errors, Qdrant/Redis
Compose infrastructure, canonical verification commands, and GitHub Actions quality/integration
jobs.

## In progress

### Phase 2 — Corpus contracts, fixtures, data governance, and evaluation split

Branch: `phase-02-corpus-contracts`.

Scope:
- corpus manifest and split contracts;
- PDF/DOCX/HTML discovery without parsing;
- SHA-256 duplicate detection;
- deterministic corpus/evaluation fingerprints;
- development/evaluation leakage enforcement;
- mixed-format real fixtures;
- CLI inspection/validation;
- cumulative Phase 1 regression verification.

Phase 2 is not complete until its branch passes quality, fixture integration, service-backed
integration, package smoke, and the complete cumulative pytest suite.

## Later phases

Parsing/OCR, cleaning, chunking, retrieval, reranking, generation, evaluation, serving,
observability, deployment, and release validation remain intentionally unimplemented until their
respective phases.
