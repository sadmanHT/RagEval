# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is to make retrieval and generation quality measurable, reproducible, and debuggable.

## Phase 1 status

This branch establishes the repository foundation: typed contracts, provider interfaces, deterministic IDs, safe settings/logging, test tiers, local Qdrant/Redis infrastructure, and CI quality gates.

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

`make verify` runs linting, formatting checks, type checking, and unit tests. `make integration` starts Qdrant and Redis and runs service-backed integration tests. `make smoke` runs the package smoke test.

## Architecture principles

- Hosted services are adapters behind explicit protocols, never hard-wired dependencies.
- Deterministic tests are the acceptance baseline; live-provider checks are an additional tier.
- Benchmark and evaluation numbers must come from actual runs, never from documentation constants.
- Every phase must pass its own tests and the cumulative regression suite before completion.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, and `docs/plans/phase-01-foundation.md` for details.
