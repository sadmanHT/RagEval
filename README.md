# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is
to make retrieval and generation quality measurable, reproducible, and debuggable.

## Current status

Phase 1 (foundation and quality gates) is merged and verified on `main`. Phase 2 adds the
corpus/data-governance layer: portable manifests, streaming checksums, deterministic
fingerprints, duplicate evidence, held-out split leakage protection, and real mixed-format
fixtures.

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

The corpus layout is `<root>/<development|evaluation>/<financial|legal|research>/<file>`.
Supported Phase-2 discovery formats are PDF, DOCX, HTML, and HTM.

## Architecture principles

- Hosted services are adapters behind explicit protocols, never hard-wired dependencies.
- Deterministic tests are the acceptance baseline; live-provider checks are an additional tier.
- Benchmark and evaluation numbers must come from actual runs, never from documentation constants.
- Evaluation sources must remain held out by identity and checksum, including renamed duplicates.
- Every phase must pass its own tests and the cumulative regression suite before completion.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, and `docs/plans/`.
