# RAG-Eval — Engineering Case Study

RAG-Eval is an evaluation-first Retrieval-Augmented Generation system built to explore the parts of RAG that are usually skipped in demos: retrieval composition, provenance, grounding, repeatable evaluation, serving boundaries, observability, failure recovery, and release evidence.

This document is the portfolio-oriented technical narrative. The phase reports under `docs/phases/` remain the detailed implementation record.

## Problem

A minimal RAG demo can retrieve a few chunks and send them to an LLM. That is not enough to answer the engineering questions that matter once the system becomes a product:

- Which retrieval path produced the evidence?
- Can dense and sparse retrieval be combined without mixing incompatible score scales?
- Can a generated citation always be traced back to a canonical source chunk?
- What happens when context is insufficient?
- Can evaluation runs resume and remain comparable across configurations?
- Can the API degrade visibly when Qdrant or another dependency fails?
- Can operational telemetry stay useful without exporting raw document content?
- Can a frontend expose the system without receiving backend credentials or reimplementing RAG logic?

RAG-Eval treats those questions as the core system rather than follow-up polish.

## Design constraints

### One canonical data path

Document and chunk identities are deterministic and derived from canonical content/configuration inputs. Dense retrieval, sparse retrieval, RRF fusion, reranking, multi-hop retrieval, context assembly, citations, evaluation records, cache identity, and telemetry all preserve the same provenance chain.

The practical benefit is debuggability: evidence shown to a user can be connected back to the same chunk identity used by retrieval and evaluation instead of passing through parallel representations.

### Retrieval components remain composable

The retrieval service orchestrates dense and sparse retrieval, hybrid fusion, reranking, optional query expansion, and bounded multi-hop behavior. Reciprocal Rank Fusion combines ranked lists instead of treating dense similarity and BM25 scores as if they shared one numeric scale.

Reranking and multi-hop behavior sit behind the same retrieval-service boundary rather than creating separate query paths. Diagnostics can therefore retain the evidence that existed before and after each stage.

### Grounding is enforced as a contract

Generation consumes assembled context built from retrieved canonical chunks. Citations are validated against chunk IDs supplied to the generation boundary, and unsupported questions can return an explicit insufficient-context refusal instead of inventing an answer.

The deterministic fixture path validates both answerable grounded responses and refusal behavior with zero citations when support is absent.

### Evaluation is part of the system

The evaluation layer is not a notebook-only afterthought. The asynchronous runner supports bounded concurrency, retry behavior, per-example checkpoints, resumability, configuration matrices, aggregate/per-domain summaries, failure classification, regression policies, and machine-readable report artifacts.

This makes evaluation callable from both CI/release validation and the product console while preserving one canonical backend implementation.

### Hosted providers are adapters, not acceptance dependencies

Provider boundaries are typed protocols. Deterministic local/fake implementations satisfy those contracts for acceptance tests, while hosted providers can be configured as an additional validation tier.

That separation lets CI prove orchestration, identity, retry, grounding, failure handling, and evaluation mechanics without making claims about hosted-model quality when credentials or representative datasets are unavailable.

## Serving and security boundary

FastAPI is the canonical serving layer. It provides authenticated grounded query execution, liveness/readiness, evaluation job submission/status, streaming responses, request limits, rate limiting, and Redis-backed caching.

The Next.js frontend is intentionally thin. Browser code calls same-origin route handlers; those server-side handlers attach the FastAPI API key. Retrieval, generation, evaluation, authentication policy, and corpus logic remain in Python.

Operational safeguards include non-root containers, reduced Linux capabilities/read-only filesystem constraints in Compose, safe error handling, bounded metric cardinality, and tracing defaults that do not export raw document/context text.

## Observability and failure recovery

Prometheus metrics and a provisioned Grafana dashboard expose request rate, latency, cache behavior, evaluation queue state, provider failures, and dependency readiness.

The container validation path deliberately stops Qdrant, verifies readiness degradation and the corresponding dependency metric, restarts Qdrant, and verifies readiness recovery. The recovery contract is therefore exercised instead of documented only as an aspiration.

## Validation strategy

RAG-Eval separates evidence tiers so deterministic fixtures are not presented as representative production quality.

The connected local release validator exercises 15 deterministic/adversarial scenarios spanning financial, legal, and research fixtures, including query expansion, multi-hop retrieval, insufficient-context refusal, provider retry/timeout behavior, evaluation resume, index rebuild, concurrency, tracing/metrics redaction, cache invalidation, and installed-Tesseract OCR.

The current repository also validates real local Qdrant and Redis integration, non-root runtime behavior, frontend production build and proxy smoke, and containerized outage/recovery mechanics.

The committed fixtures are intentionally small. They support claims about contracts, orchestration, traceability, arithmetic, resilience, and release mechanics. They do **not** establish a production retrieval winner, production hallucination rate, production SLO, or hosted-model quality level.

The representative roughly 12,000-document corpus, target roughly 200-question reviewed evaluation set, and hosted-provider credentials are not committed to this repository.

## Tradeoffs

### Deterministic acceptance vs. representative quality

A deterministic local gate is reproducible and available on every PR, but it cannot replace representative domain evaluation. RAG-Eval keeps the deterministic gate authoritative for correctness/mechanics while treating larger reviewed datasets and live providers as separate evidence layers.

### In-process evaluation jobs vs. durable orchestration

The serving layer uses a bounded in-process evaluation queue. This keeps the local product and validation topology compact, but it is not a durable distributed job system. A production deployment that needs persistence or horizontal worker scaling would move this boundary to a durable queue without changing the evaluation runner itself.

### Local Prometheus scraping vs. production network policy

`/metrics` is intentionally simple for local Compose usage. Production deployment must restrict that endpoint at the edge/network layer rather than assuming the local topology is already a hardened production network design.

### Reindex-first Qdrant recovery

The validated recovery story is reindex-first. Environment-specific snapshot restore is not claimed because it has not been proven in this repository's acceptance path.

## What I would do next

The highest-value next work is evidence and deployment specific rather than another retrieval implementation:

1. Run the existing evaluation matrix against the representative corpus and reviewed question set.
2. Execute live embedding/reranking/generation provider tiers with recorded latency, quality, and cost evidence.
3. Establish statistically useful production drift and SLO baselines.
4. Move evaluation jobs to durable orchestration if production workload requires it.
5. Deploy the existing API/frontend/observability topology behind environment-specific secrets, TLS, network policy, and autoscaling controls.

## Where to inspect the implementation

- `src/rageval/retrieval/service/` — canonical retrieval orchestration
- `src/rageval/generation/` — context assembly, grounded generation, citation validation
- `src/rageval/evaluation/` — metrics, runners, checkpoints, comparisons, reporting
- `src/rageval/serving/` — FastAPI boundary, cache, health, jobs, limits
- `src/rageval/observability/` — traces and Prometheus instrumentation
- `web/` — thin Next.js product console/BFF
- `scripts/full_system_validation.py` — connected-system acceptance runner
- `docs/phases/phase-15-report.md` — detailed release evidence and limitations
