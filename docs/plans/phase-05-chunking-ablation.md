# Phase 5 — Chunking Engine, Table Awareness, and Ablation Harness

## Mission

Implement interchangeable, measurable chunking strategies on top of the Phase 4 `CleanedDocument`
boundary without reparsing or recleaning source files. Preserve source provenance and table meaning,
and do not choose a globally preferred strategy without later retrieval/evaluation evidence.

## Scope

- fixed-token reference configurations: 256/32, 512/64, and 1024/128 size/overlap;
- semantic sentence-boundary chunking behind the existing embedding-provider protocol;
- deterministic similarity-policy injection for unit tests and offline mechanics validation;
- table-aware handling that keeps small tables whole and splits oversized tables only by whole row
  groups with repeated headers;
- practical legal-clause and configurable section-aware boundaries;
- deterministic chunk IDs and behavior-complete chunking configuration fingerprints;
- source pages, cleaned/source element IDs, domain, table/source coordinates, and cleaning
  fingerprint provenance carried into chunk metadata;
- a debug chunking CLI that does not index;
- a machine-readable ablation harness reporting chunk counts, token distributions, overlap, table
  fragmentation, and provenance coverage per strategy/domain;
- cumulative Phase 1–4 verification plus a permanent Phase 5 fixture-ablation CI gate.

## Acceptance rules

1. All four reference strategies use one `ChunkingEngine` boundary and the existing shared `Chunk`
   contract.
2. Fixed-window overlap is exact and deterministic.
3. Semantic split tests use injected deterministic embeddings that force known boundaries.
4. No table row or cell is split merely to satisfy a token maximum. An atomic oversized row may
   exceed the configured target rather than become uninterpretable.
5. Later table groups repeat the header when configured and retain table/page/source metadata.
6. Cleaned source elements must have complete chunk provenance coverage, excluding non-content page
   breaks/empty elements.
7. Chunk/config identities are deterministic and configuration-sensitive.
8. The ablation output is JSON-serializable and records a deterministic dataset fingerprint.
9. Fixture statistics are evidence only for the committed small corpus; they cannot establish a
   globally optimal chunking strategy.
10. The local hashed embedding adapter is deterministic offline mechanics evidence only, not a
    learned semantic-model benchmark.
11. No prior test, static-check, cleaning gate, service check, or installed-Tesseract OCR gate may
    be weakened.

## Verification

Canonical commands/gates:

```bash
ruff check .
ruff format --check .
mypy src
pytest -q tests/unit
docker compose config
docker compose up -d qdrant redis
pytest -q tests/integration
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

The dedicated CI OCR job separately installs Tesseract and runs the real image-only PDF fixture.

## Handoff target

Phase 6 must consume Phase 5 `Chunk` outputs and their deterministic IDs/configuration fingerprints
for embedding and Qdrant dense retrieval. It must preserve chunk metadata needed for payload
filters, citations, evaluation attribution, and later index rebuilds. Phase 6 must not silently
hard-code a single winning chunk strategy; index/evaluation configuration must identify which
Phase 5 chunking configuration produced each collection.
