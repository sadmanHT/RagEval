# Phase 15 Post-Merge Closure

Phase 15 — Full-System Validation, Benchmarking & Release Readiness — is merged and independently revalidated on `main`.

## Merge evidence

- Pull request: **#23 — Phase 15: full-system validation, benchmarking, and release**
- Final report-bearing PR head: `10d352bff0cf0dd1b92afe8e8a55086fd61a39df`
- Exact PR-head CI: GitHub Actions run `34855291806`
- PR-head result: all six jobs passed (`quality`, `integration`, `container`, `security`, `local-ocr`, `release-validation`)
- Merge commit: `984fc627da264ce27c3ce092906f938ce81c9db0`
- Independent merge-triggered `main` CI: run `34855636932`
- Post-merge result: all six jobs passed independently, including the complete container validator and Qdrant outage/recovery drill.

The merge used the exact validated PR head as the expected-head lock. No later unvalidated PR commit was merged.

## Accepted implementation evidence

The Phase 15 acceptance layer composes the existing canonical RAG stack; it does not create a parallel retrieval or generation implementation. The release validator covers financial, legal, and research end-to-end queries together with table-aware retrieval, vocabulary-mismatch query expansion, bounded two-hop retrieval, insufficient-context refusal, mocked provider retry/timeout, Self-RAG routing invariants, evaluation checkpoint resume, index rebuild, modest API concurrency, tracing/metrics redaction, cache invalidation after index identity change, and installed-Tesseract OCR.

Validated counts on the accepted implementation:

- Ruff lint and formatting passed;
- strict mypy passed on **92 source files**;
- **184 unit tests passed**;
- ordinary integration: **31 passed, 1 skipped**;
- host cumulative suite: **215 passed, 1 skipped**;
- the skip is the intentional local-OCR test in a host job without Tesseract;
- Tesseract-enabled container cumulative suite: **216 passed**;
- dedicated installed-Tesseract OCR passed;
- non-root runtime UID: **10001**;
- dependency auditing and secret scanning passed;
- Qdrant outage produced degraded readiness and `rageval_dependency_ready{component="qdrant"} 0.0`;
- Qdrant restart restored healthy readiness and the metric to `1.0`.

## Release-validation artifact

The authoritative implementation artifact was produced by run `34852249615` from exact implementation SHA `31cc3f8bbcceb07a38672d1f8bc197347f99ec5f`.

- artifact name: `phase15-release-evidence-34852249615`
- artifact ID: `10351304010`
- digest: `sha256:75f0b84e390c6da6d8fb707494857750bce5a2c34f6cc7719e2120af51e40cac`
- evidence label: `phase15-local-full-system-fixture-evidence-only`
- source documents: **4**
- canonical chunks: **6**
- deterministic/adversarial scenarios: **15 passed**
- release gate: `true`

The report-bearing PR head reran the same release-validation job successfully in run `34855291806`, and the merge commit reran it independently on `main` in run `34855636932`.

## Measured fixture benchmark

The authoritative implementation artifact used Python 3.11.16 on a GitHub-hosted Linux x86_64 runner with eight cold API samples, eight warm-cache samples, and twelve concurrent requests at configured query concurrency four.

Observed values:

- cold API p50: `5.794 ms`
- cold API p95/p99: `6.026 ms`
- cold retrieval p50: `5.463 ms`
- cold retrieval p95/p99: `5.654 ms`
- cold generation p50: `0.280 ms`
- cold generation p95/p99: `0.310 ms`
- warm Redis-cache API p50: `0.344 ms`
- warm Redis-cache API p95/p99: `0.462 ms`
- modest-concurrency run: `187.14 requests/second`, p95 `58.05 ms`

These are runner-local deterministic fixture observations, not production SLOs, capacity guarantees, hosted-provider latency claims, or representative workload benchmarks.

## Evaluation and ablation boundary

The available reviewed set contains **3 records**, not the target roughly 200-question held-out set. The target set was not fabricated.

The Phase 15 support/reference-backed mechanics evaluator completed without a hallucination flag on those three records and the second execution resumed all three checkpoints. The inherited Phase 11 deterministic-rule fixture independently flags one of three. These are different deterministic fixture paths and neither is a representative production hallucination-rate estimate.

The five-configuration reconciliation uses the preserved run/checkpoint/report evidence and an equal-weight composite over context precision, context recall, faithfulness, and answer relevancy per domain. The tiny set produces fixture-local ties:

- financial: fixed-1024, semantic, and table-aware tie;
- legal: fixed-1024 and table-aware tie;
- research: fixed-1024, semantic, and table-aware tie.

No production chunking strategy is selected from one reviewed example per domain.

## Explicit release limitations

The following remain outside the evidence of Phase 15 and the deterministic `v0.1.0` release candidate:

1. representative roughly 12,000-document corpus;
2. target roughly 200-question reviewed evaluation set;
3. live OpenAI/Cohere/Langfuse/W&B/RAGAS acceptance without deliberately supplied credentials;
4. production load, throughput, SLO, or cost benchmarking;
5. statistically significant drift validation;
6. distributed/global rate limiting and durable distributed evaluation-job state;
7. production network restriction for the intentionally unauthenticated local `/metrics` scrape endpoint;
8. production deployment topology/credentials beyond the local Compose stack;
9. fully hash-locked Python dependency supply chain;
10. environment-proven Qdrant snapshot restore beyond the documented reindex-first recovery path;
11. a ColPali/vision-table adapter, which is not present in the current roadmap implementation;
12. upstream FastAPI/Starlette/httpx2/AnyIO and GitHub Actions Node-version deprecation warnings.

## Final closure gate

This post-merge record, the README status update, and the implementation-state update form the Phase 15 closure documentation. The exact final documentation-bearing `main` head must pass all six CI jobs before Phase 15 is declared closed. Only after that final green run may `v0.1.0` be created, and the tag/release must point to that exact final closure commit.
