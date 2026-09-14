# Phase 14 — Observability, Docker/Compose, CI/CD, Security & Operational Hardening

## Project context the agent must preserve

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose main differentiator is rigorous measurement. It is not merely a document-chat application. The system must ingest mixed-format financial reports, legal contracts, and research papers; clean and chunk them; index them for dense and sparse retrieval; fuse results; rerank them; generate grounded answers with chunk-level citations; and continuously evaluate retrieval and generation quality.

Target architecture:
- **Ingestion:** PDF/DOCX/HTML parsing with Unstructured-style element extraction, OCR fallback for scanned content, normalization, metadata preservation, and table-aware handling.
- **Chunking:** fixed-token 256/512/1024 strategies plus semantic chunking; the implementation must support controlled ablations. Because table fragmentation is a known failure mode, the production implementation should also support table-aware boundary preservation.
- **Dense retrieval:** Qdrant with cosine similarity, payload filters, configurable HNSW/index settings, and an embedding-provider abstraction. The reference document describes OpenAI `text-embedding-3-large` at 3072 dimensions.
- **Sparse retrieval:** BM25/BM25+ style retrieval with a domain-aware tokenizer and top-k candidate retrieval.
- **Fusion:** Reciprocal Rank Fusion, default smoothing constant `k=60`, combining dense and sparse rankings without naïve score normalization.
- **Reranking:** a cross-encoder reranker, with Cohere Rerank as the reference hosted provider, reducing the fused candidate set to the final context set.
- **Generation:** provider-abstracted LLM invocation, top retrieved chunks assembled into a structured context, strong grounding instructions, refusal when context is insufficient, and chunk-ID citations for claims.
- **Evaluation:** a held-out evaluation set, context precision, context recall, faithfulness, answer relevancy, and a clearly defined hallucination-rate calculation. LLM-as-judge functionality must use structured outputs, explicit rubrics, repeatable inputs, and auditable results.
- **Serving:** async FastAPI, typed Pydantic schemas, API-key authentication, query/evaluation endpoints, caching where safe, and optional streaming.
- **Observability:** Langfuse-style traces, Prometheus metrics, Grafana dashboards, cost/latency accounting, and evaluation trend tracking.
- **Infrastructure:** Docker/Compose, Redis, Qdrant, CI/CD, reproducible local development, and separate deterministic tests from credential-dependent live-provider tests.
- **Core philosophy:** measure first, optimize second. No architecture change is considered an improvement without evaluation evidence.

The reference documentation mentions a roughly 12,000-document corpus across financial reports, legal contracts, and research papers, and a 200-question held-out evaluation set. Treat those as project targets. Do not fabricate corpus contents, benchmark numbers, or model-provider results when the actual data or credentials are absent.

The original document also contains claims that need evidence-based reconciliation during implementation:
1. A binary hallucination rate over exactly 200 questions must be arithmetically consistent with the count of hallucinated responses. Never hard-code inconsistent percentages.
2. The document gives conflicting statements about the preferred chunking strategy for financial data. Resolve this by running ablations and recording actual per-domain results.
3. Two ablation rows in the document have identical metrics despite allegedly adding semantic chunking. The implementation must generate real configuration-specific results.
4. The document mentions both MLflow and Weights & Biases for experiment trends. Use one primary experiment-tracking abstraction/configuration and document the choice; do not silently duplicate responsibilities.
5. “No cloud credentials required” is only valid if embeddings, reranking, and generation all have local/offline paths. Either implement complete local-provider fallbacks or document which capabilities require credentials.
6. A nightly post-merge evaluation cannot literally block a pull request. CI gates and nightly regression jobs must be designed consistently.

## Non-negotiable execution contract

You are implementing this phase inside the existing repository, not writing a theoretical answer.

1. **Inspect first.** Read the current repository, prior phase reports, tests, configuration, and git diff before changing anything. Reuse working abstractions instead of creating parallel systems.
2. **No premature success.** A build, import, or happy-path demo is not enough. A phase is complete only after its own tests **and every relevant test from all previous phases** pass together.
3. **Regression is cumulative.** After implementing the phase, run the full unit suite, integration suite, static checks, and the project smoke test. If anything fails, diagnose it, fix the root cause, and rerun the affected tests plus the full regression suite. Continue until green or until there is a genuine external blocker.
4. **Do not hide failures.** Do not delete tests, weaken assertions, add broad `xfail`, catch-and-ignore exceptions, or mock away the behavior under test just to get green CI. Any unavoidable skipped live-provider test must have an explicit reason and remain separate from deterministic acceptance.
5. **Determinism first.** External APIs must sit behind interfaces. Unit/integration tests use deterministic fakes or recorded fixtures. Live OpenAI/Cohere/Anthropic/Langfuse/W&B tests are an additional tier, never the only evidence that code works.
6. **No fabricated metrics.** Do not copy the PDF’s headline scores into generated reports. Only persist numbers produced by an actual run, with configuration, dataset fingerprint, model/provider versions, and timestamp.
7. **Keep contracts stable.** Public dataclasses/Pydantic schemas, chunk IDs, metadata fields, retrieval result fields, and CLI/API response shapes must be versioned or migrated deliberately when changed.
8. **Quality bar.** Code must be typed, readable, modular, async-safe where appropriate, documented at public boundaries, and free of obvious placeholder/TODO implementations in the phase scope.
9. **Evidence.** At the end of the phase, write/update a repository phase report containing: files changed, architecture decisions, commands run, test counts/results, known limitations, provider tests run or blocked, and the exact handoff state for the next phase.
10. **Truthful completion.** If credentials, GPU access, or the real corpus are unavailable, complete and test the deterministic/local path and explicitly record the blocked live validation. Never call a blocked check “passed.”

### Standard verification loop

Use the repository’s canonical commands created in Phase 1. The intended shape is:

```bash
ruff check .
ruff format --check .
mypy .
pytest -q tests/unit
pytest -q tests/integration
pytest -q
docker compose config
# when integration services are required:
docker compose up -d qdrant redis
pytest -q tests/integration
# phase-specific smoke/e2e command
```

If the repository later exposes `make verify`, `make integration`, `make smoke`, or equivalent task-runner commands, prefer those canonical commands. Every phase must leave the repository in a state where a new agent can reproduce the verification from a clean checkout.

## Phase-specific plan

### Mission
Make the system diagnosable and reproducible as an operated service, not just a working Python package.

### Required implementation
- Langfuse-compatible tracing adapter capturing query, branch candidates/ranks, RRF, reranking, context assembly, generation metadata, citation validation, evaluation linkage, and per-stage latency. Redact secrets and sensitive raw content according to configuration.
- Prometheus metrics for request count/error count, p50/p95/p99-capable latency histograms, retrieval/generation/evaluation durations, cache hit rate, provider failures, token/cost counters where available, and queue/job status.
- Grafana dashboard provisioning for key metrics.
- Implement embedding/query drift hooks based on safe aggregate distributions; do not claim statistical significance without enough data.
- Dockerfile with non-root runtime, healthcheck, minimal image, pinned/reproducible build inputs where practical.
- Docker Compose for API, Qdrant, Redis, Prometheus, Grafana, and optional local-model services. Langfuse may be external or locally composed, but the choice must be explicit.
- CI:
  - lint/format/type/unit on every PR;
  - deterministic integration tests with service containers;
  - Docker build and container smoke on PR;
  - fast evaluation subset gate on PR using stable fixtures or an approved small eval subset;
  - full evaluation on schedule/manual trigger, producing artifacts and regression alerts.
- Correct the original inconsistency: a nightly post-merge job reports/alerts/regresses against releases; only checks that actually run before merge can be merge blockers.
- Add dependency/security scanning, secret scanning, API abuse/rate-limit policy, and safe CORS defaults as appropriate.
- Add backup/restore or reindex strategy documentation for Qdrant and persisted evaluation artifacts.

### Testing required in this phase
- Trace-adapter unit tests verify fields/redaction.
- Prometheus endpoint tests and metric-label cardinality sanity.
- Docker build from clean context; run container as non-root; readiness passes with services.
- `docker compose up` end-to-end smoke from clean volumes.
- Simulate dependency outage and verify useful metrics/logs plus correct readiness behavior.
- Validate CI workflow syntax and, where possible, execute equivalent commands locally.
- Security tests for missing auth, oversized input, obvious header abuse, secret leakage, and unsafe CORS configuration.
- Run the **entire** repository suite in the containerized environment.

### Phase completion gate
A clean machine with Docker and documented credentials must be able to start the stack, run the deterministic test suite, query the service, inspect metrics, and reproduce the operational smoke test.
