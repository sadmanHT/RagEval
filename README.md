# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is to make retrieval and generation quality measurable, reproducible, and debuggable.

## Current status

Phases 1–6 are merged and verified on `main`. The current pipeline covers repository/quality foundations, deterministic corpus governance, normalized PDF/DOCX/HTML loading with explicit OCR fallback, provenance-preserving cleaning, interchangeable chunking strategies, and reproducible dense retrieval over versioned Qdrant collections.

Phase 6 dense retrieval consumes canonical Phase 5 chunks, embeds them behind a replaceable provider boundary, preserves stable chunk/configuration/provenance identity in reconstructable Qdrant payloads, and returns the existing canonical `RetrievalResult` contract. It supports domain, source-date, document, and chunking-configuration filters; deterministic idempotent point identity; document replace/delete/consistency operations; configurable HNSW/search parameters; and explicit stale-vector-schema errors.

The deterministic/local acceptance path uses a 64-dimensional local hashed embedding adapter for mechanics and real-Qdrant integration only. The hosted reference adapter targets OpenAI `text-embedding-3-large` with a 3072-dimensional default, but no live OpenAI result is claimed without an actual credential-enabled run.

Chunking continues to support fixed 256/32, 512/64, and 1024/128 configurations plus provider-injected semantic splitting and table-aware whole-row boundaries. The small committed fixtures verify mechanics/provenance rather than selecting a globally optimal chunking or embedding strategy.

Phase 7 — BM25 sparse retrieval — is next.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
make verify
make integration
make dense-report
make smoke
```

Inspect a corpus without parsing document contents:

```bash
python -m rageval.corpus.cli scan ./data/raw --output ./data/corpus-manifest.json
python -m rageval.corpus.cli validate ./data/corpus-manifest.json --root ./data/raw
```

Parse one source into normalized debug JSON without indexing:

```bash
python -m rageval.ingestion.cli file ./data/raw/development/financial/report.pdf \
  --domain financial --output ./tmp/report.elements.json
```

Parse a manifest subset:

```bash
python -m rageval.ingestion.cli corpus ./data/corpus-manifest.json \
  --root ./data/raw --output-dir ./tmp/elements --split development
```

Parse, clean, and chunk one source without indexing:

```bash
python -m rageval.chunking.cli ./data/raw/development/financial/report.pdf \
  --domain financial --strategy fixed_512 --output ./tmp/report.chunks.json
```

For offline semantic mechanics/debugging, the Phase 5 semantic CLI uses the deterministic local hashed embedding adapter rather than claiming a hosted or learned semantic-model result:

```bash
python -m rageval.chunking.cli ./data/raw/evaluation/research/paper.html \
  --domain research --strategy semantic --output ./tmp/paper.semantic-chunks.json
```

Reproduce the deterministic fixture evidence used by CI:

```bash
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
python scripts/dense_fixture_report.py
```

The dense fixture report starts from the committed source fixtures, parses/cleans/chunks them, indexes them in a real local Qdrant container, verifies consistency and filters, performs canonical retrieval sanity checks, emits machine-readable JSON, and deletes its temporary collection.

The corpus layout is `<root>/<development|evaluation>/<financial|legal|research>/<file>`.
Supported discovery/parsing formats are PDF, DOCX, HTML, and HTM.

## Architecture principles

- Hosted services are adapters behind explicit protocols, never hard-wired dependencies.
- Deterministic tests are the acceptance baseline; live-provider checks are an additional tier.
- Benchmark and evaluation numbers must come from actual runs, never from documentation constants.
- Evaluation sources must remain held out by identity and checksum, including renamed duplicates.
- Parser libraries never leak raw objects beyond the ingestion boundary.
- OCR fallback is explicit, configurable, observable, and separately validated with a real local Tesseract path.
- Cleaning is configuration-fingerprinted, auditable, and conservative about deleting repeated answer-bearing body content.
- Chunking consumes cleaned elements, preserves table/source provenance, and fingerprints every behavior-affecting configuration.
- Dense indexing preserves canonical chunk IDs/configuration/provenance, validates collection schemas before reuse, and keeps external embeddings behind replaceable providers.
- Local-hash dense evidence validates mechanics, not learned semantic quality; live-provider and representative retrieval-quality evidence must be reported separately when actually run.
- No chunking or retrieval strategy is considered preferable without representative evaluation evidence.
- Every phase must pass its own tests and the cumulative regression suite before completion.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, `docs/phases/`, and `docs/plans/`.
