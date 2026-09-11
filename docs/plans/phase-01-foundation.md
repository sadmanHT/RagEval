# Phase 1 — Repository Foundation, Architecture Contracts & Quality Gates

## Mission

Create a reproducible, typed Python 3.11+ project foundation and define the architectural contracts that every later phase will build against. The main deliverable is not business functionality yet; it is a repository that makes it difficult to accidentally build untestable or tightly coupled RAG code.

## Required implementation

- Establish/repair `pyproject.toml` with runtime and dev dependency groups.
- Create package namespaces for ingestion, retrieval, generation, evaluation, serving, shared core/models, scripts, tests, and docs.
- Add typed environment settings and `.env.example`; never commit secrets.
- Define canonical contracts for documents, elements, chunks, retrieval/rerank results, grounded answers, citations, evaluation examples/results, and provider protocols.
- Use deterministic document/chunk ID rules.
- Define typed error classes and structured secret-redacting logging.
- Add Ruff, mypy, pytest/pytest-asyncio/coverage and canonical task-runner commands.
- Add Qdrant and Redis through Docker Compose.
- Add deterministic fixtures/test helpers and implementation-state documentation.

## Non-negotiable quality gate

A build/import is not sufficient. Run lint, formatting checks, type checks, unit tests, local-service integration tests, package smoke tests, and the full cumulative suite. Do not delete or weaken tests to get green CI. Hosted providers remain behind interfaces and live-provider tests are additional evidence, not deterministic acceptance.

## Evidence policy

Do not copy benchmark numbers from the reference document into generated reports. Later phases must generate real metrics with dataset/config/model fingerprints. Do not claim full offline operation until embeddings, reranking, and generation all have tested local adapters.

## Completion gate

Do not proceed until a clean checkout can install dependencies, import the package, start local infrastructure, and pass the entire Phase 1 suite with exact commands and versions recorded in the phase report.
