# Implementation State

## Current phase

**Phase 1 — Repository Foundation, Architecture Contracts & Quality Gates**

Status: **in progress until branch CI is green**.

### Implemented in this phase

- `src/rageval` package foundation and subsystem namespaces.
- Pydantic contracts for documents, elements, chunks, retrieval/rerank outputs, grounded answers, citations, and evaluation records.
- Async provider protocols and deterministic fake implementations.
- Environment-based typed settings with conditional provider-secret validation.
- Deterministic ID/fingerprint helpers.
- Typed error hierarchy.
- JSON logging with secret redaction.
- Ruff, mypy, pytest, coverage, Makefile verification commands.
- Docker Compose services for Qdrant and Redis.
- Unit and infrastructure integration tests.
- GitHub Actions workflow for cumulative Phase 1 checks.

### Not yet implemented

Parsing, chunking algorithms, embedding/indexing logic, retrieval, reranking, generation, evaluation execution, API serving, production observability, and benchmark claims belong to later phases.

### Truthful offline status

Phase 1 defaults to deterministic fake providers. It does **not** claim that the final RAG stack is fully usable without cloud credentials. Later phases must either add local adapters for embeddings/reranking/generation or document their credential requirements.
