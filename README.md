# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is
to make retrieval and generation quality measurable, reproducible, and debuggable.

## Current status

Phases 1–5 are merged and verified on `main`. The current pipeline covers repository/quality
foundations, deterministic corpus governance, normalized PDF/DOCX/HTML loading, explicit OCR
fallback, provenance-preserving cleaning, and interchangeable chunking strategies. Phase 6 is the
active implementation phase for embeddings, Qdrant indexing, and dense retrieval.

Chunking supports the reference fixed configurations 256/32, 512/64, and 1024/128 together with
provider-injected semantic sentence-boundary chunking. Table awareness keeps complete small tables
together and splits oversized tables only on whole-row groups with repeated headers, preserving
source page/element/table provenance. Legal numbered clauses and section hints can also create
conservative boundaries.

Phase 5 deliberately does not declare a globally optimal strategy. The committed fixtures are too
small to distinguish the reference sizes; their role is to verify mechanics, table integrity, and
provenance. Semantic fixture evidence uses a deterministic local hashed embedding adapter and is not
a learned-model benchmark.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
make verify
make integration
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

For offline semantic mechanics/debugging, use the semantic strategy; the CLI uses the deterministic
local hashed embedding adapter rather than claiming a hosted or learned semantic-model result:

```bash
python -m rageval.chunking.cli ./data/raw/evaluation/research/paper.html \
  --domain research --strategy semantic --output ./tmp/paper.semantic-chunks.json
```

Reproduce the deterministic fixture evidence used by CI:

```bash
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
```

The corpus layout is `<root>/<development|evaluation>/<financial|legal|research>/<file>`.
Supported discovery/parsing formats are PDF, DOCX, HTML, and HTM.

## Architecture principles

- Hosted services are adapters behind explicit protocols, never hard-wired dependencies.
- Deterministic tests are the acceptance baseline; live-provider checks are an additional tier.
- Benchmark and evaluation numbers must come from actual runs, never from documentation constants.
- Evaluation sources must remain held out by identity and checksum, including renamed duplicates.
- Parser libraries never leak raw objects beyond the ingestion boundary.
- OCR fallback is explicit, configurable, observable, and separately validated with a real local
  Tesseract path.
- Cleaning is configuration-fingerprinted, auditable, and conservative about deleting repeated
  answer-bearing body content.
- Chunking consumes cleaned elements, preserves table/source provenance, and fingerprints every
  behavior-affecting configuration.
- A chunking strategy is not considered preferable without representative retrieval/evaluation
  evidence; fixture mechanics alone cannot choose a winner.
- Every phase must pass its own tests and the cumulative regression suite before completion.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, `docs/phases/`, and
`docs/plans/`.
