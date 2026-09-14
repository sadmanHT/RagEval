# Phase 12 — Full Evaluation Runner, Ablations, Experiment Tracking & Failure Analysis

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
Turn individual metrics into an operational evaluation pipeline that compares configurations, detects regressions, and explains failures.

### Required implementation
- Implement async/batched evaluation runner with bounded concurrency, retries, checkpoints/resume, and per-example persistence.
- Support configuration matrices for:
  - dense-only baseline;
  - dense + BM25/RRF;
  - hybrid + rerank;
  - chunking strategies (256/512/1024/semantic/table-aware);
  - query expansion on/off;
  - multi-hop on/off where applicable.
- Record full run metadata: git commit, dataset fingerprint, corpus/index fingerprint, provider/model versions, prompt versions, chunk config, retrieval params, timestamp, machine/environment summary.
- Aggregate by overall and domain (`financial`, `legal`, `research`) metrics.
- Add confidence intervals or at least sample counts; never overstate tiny differences.
- Implement failure taxonomy tooling for table fragmentation, vocabulary mismatch, long-range references, retrieval miss, reranker error, citation failure, generation unsupported claim, and unknown.
- Standardize experiment tracking on the Phase 1 choice (prefer W&B adapter). A local JSON/SQLite report must still be produced when cloud tracking is disabled.
- Add regression comparator that can enforce configured thresholds. Threshold logic must distinguish PR-fast-eval gates from nightly/full-eval alerts.
- Generate human-readable Markdown/HTML and machine-readable JSON reports.

### Testing required in this phase
- Resume after injected failure without duplicating completed examples.
- Concurrency limit tests and deterministic aggregation.
- Configuration matrix produces distinct labeled runs; duplicate config IDs are rejected.
- Regression comparator tests for improvement, degradation, missing metric, and sample-size mismatch.
- Failure-taxonomy fixture tests.
- Local report and experiment-tracker fake tests.
- Run a small full ablation on fixtures and verify the report values are recomputed from records.
- Full regression suite.

### Phase completion gate
The project must be capable of executing repeatable comparative evaluations and producing evidence that can resolve the original documentation’s conflicting chunking/ablation claims. Do not overwrite reference documentation with new numbers until an actual representative run has been completed.
