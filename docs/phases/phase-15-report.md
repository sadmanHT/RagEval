# Phase 15 Report — Full-System Validation, Benchmarking & Release Readiness

Status: implementation acceptance evidence is green on PR #23 at exact head `31cc3f8bbcceb07a38672d1f8bc197347f99ec5f`. CI run `34852249615` passed all six jobs. This report is now part of a new PR head and must itself pass the same six-job matrix before merge. Phase 15 is not closed until merge, independent `main` CI, post-merge closure documentation, final `main` CI, and release verification are complete.

## Mission outcome

Phase 15 adds a final validation layer over the existing canonical RAG system rather than introducing a second retrieval or generation path. The acceptance runner composes the repository's real fixture ingestion, cleaning, chunking, Qdrant dense retrieval, BM25 sparse retrieval, RRF hybrid fusion, reranking, grounded generation/citation validation, authenticated serving/cache boundary, checkpointed evaluation, and operational telemetry.

The deterministic release gate passed 15 end-to-end/adversarial scenarios across financial, legal, and research fixtures: domain E2E queries, table-aware retrieval, vocabulary-mismatch query expansion, two-hop retrieval, insufficient-context refusal, mocked provider retry/timeout, Self-RAG comparison, evaluation resume, index rebuild, modest API concurrency, tracing/metrics redaction, cache invalidation after index identity change, and installed-Tesseract OCR.

## Evidence boundary

All Phase 15 quality and performance numbers below are local deterministic fixture evidence only. The representative roughly 12,000-document corpus and target roughly 200-question reviewed evaluation set were not supplied. No live OpenAI, Cohere, Langfuse, W&B, or RAGAS acceptance result is claimed. The local hash embedding provider, deterministic reranker, deterministic grounded generation provider, and mocked OpenAI retry/timeout transport validate mechanics, contracts, resilience, and reproducibility; they are not representative hosted-provider quality evidence.

The current roadmap also has no ColPali/vision-table adapter. Production load/SLO/cost validation and statistically significant drift validation remain outside the evidence produced here.

## Authoritative implementation evidence

Validated implementation head: `31cc3f8bbcceb07a38672d1f8bc197347f99ec5f`

CI run: `34852249615`

Release evidence artifact: `phase15-release-evidence-34852249615`

Artifact ID: `10351304010`

Artifact digest: `sha256:75f0b84e390c6da6d8fb707494857750bce5a2c34f6cc7719e2120af51e40cac`

The machine-readable full-system report records the exact implementation SHA above, evidence label `phase15-local-full-system-fixture-evidence-only`, four source documents, six canonical chunks, 15 passed scenarios, and `release_gate_passed=true`.

## Static and regression gates

The authoritative run passed Ruff lint and format checks (`199 files already formatted`), strict mypy over `92 source files`, and `184` unit tests. Ordinary host integration passed `31` tests with one intentional local-OCR skip because Tesseract is not installed in that host job. The host cumulative suite passed `215` tests with that same one skip. The dedicated OCR job installed Tesseract and passed.

The container gate built clean runtime/test images, verified the runtime user is non-root UID `10001`, started the complete Compose operational stack, passed the operational API/Prometheus/Grafana/evaluation smoke, and passed the cumulative repository suite with Tesseract installed: `216 passed`. It then ran the real Phase 15 full-system validator in-container, forced a Qdrant outage and observed readiness degradation plus `rageval_dependency_ready{component="qdrant"} 0.0`, restarted Qdrant, and observed healthy readiness plus the metric returning to `1.0`.

Security acceptance also passed dependency audit and secret scanning.

## Full-system scenario evidence

The 15 passed scenarios are:

1. financial-domain-e2e
2. legal-domain-e2e
3. research-domain-e2e
4. table-aware-retrieval
5. vocabulary-mismatch-query-expansion
6. long-range-multi-hop
7. insufficient-context-refusal
8. provider-retry-timeout
9. self-rag-vs-always-retrieve
10. evaluation-resume
11. index-rebuild
12. api-modest-concurrency
13. tracing-and-metrics
14. cache-invalidation-after-index-identity-change
15. local-ocr-scanned-legal

Notable mechanics evidence includes query expansion recovering the research vocabulary using `Reciprocal Rank Fusion`; two retrieval hops in the long-range legal scenario; zero citations on the unsupported-question refusal; two mocked provider attempts for both retry and terminal timeout paths; first evaluation execution producing three records and the second execution resuming all three from checkpoints; an index rebuild restoring all six canonical chunks; redacted query/evaluation trace records without raw query text; and OCR execution with `used_ocr=true`.

## Measured local benchmark

The authoritative release-validation artifact was generated on Python 3.11.16 on a GitHub-hosted Linux x86_64 runner. Sample sizes were eight cold API requests, eight warm-cache requests, and twelve concurrent requests with configured query concurrency four.

Measured fixture values from that run:

- cold API: p50 `5.794 ms`, p95/p99 `6.026 ms`;
- cold retrieval: p50 `5.463 ms`, p95/p99 `5.654 ms`;
- cold generation: p50 `0.280 ms`, p95/p99 `0.310 ms`;
- warm Redis-cache API: p50 `0.344 ms`, p95/p99 `0.462 ms`;
- modest concurrent run: `187.14 requests/second`, p95 `58.05 ms` over 12 requests.

These timings are observations from one deterministic fixture runner. They are not production SLOs, capacity claims, or provider latency claims. The independent in-container run produced different timings, as expected from a different execution environment, and is used as acceptance evidence rather than the primary benchmark record.

## Evaluation and ablation reconciliation

The Phase 15 release evaluator used the three actually available reviewed fixture records. The target ~200-question set is explicitly recorded as unavailable. Dataset fingerprint: `5dad39bffb7acd7ac15414a10b9a654461a4ba0ff4642f7c66281733fd9c4cc0`.

In this Phase 15 release-evaluator path, all three records completed without a hallucination flag (`0/3`) and the second run resumed all three checkpoints. This is mechanics-only evidence over reference/support-backed fixture observations and must not be confused with the inherited Phase 11 deterministic-rule fixture path, which independently flags `1/3`. Neither number is a representative production hallucination rate.

The five-configuration reconciliation preserves the original run/checkpoint/report evidence and uses an equal-weight composite of context precision, context recall, faithfulness, and answer relevancy per domain. Matrix fingerprint: `c018635e5c3bef88954a16c063513ca6fa84812f1df5a2d2aba60a7509be7b0e`.

The three-record set produces fixture-local ties rather than a defensible production chunking winner:

- financial: fixed-1024, semantic, and table-aware tie at composite `0.9423`;
- legal: fixed-1024 and table-aware tie at `0.9250`;
- research: fixed-1024, semantic, and table-aware tie at `0.9167`.

Accordingly, Phase 15 makes no production chunking-strategy selection from this one-example-per-domain evidence.

## Provider and experiment-tracking boundary

Executed deterministically: local-hash embeddings, deterministic reranking, deterministic grounded generation, mocked OpenAI retry/timeout transport, Qdrant, Redis, Prometheus metrics, in-memory trace validation, and local JSON experiment tracking.

Blocked without external credentials/configuration: live OpenAI, Cohere, Langfuse, W&B, and RAGAS. Local JSON remains the single primary deterministic experiment-tracking path for this acceptance tier.

## Reproduction commands

Core repository gates:

```bash
make verify
make integration
make full-validation
make release-evaluation
```

Connected acceptance requires Qdrant and Redis. The container gate also validates the complete Compose stack, the Tesseract-enabled full suite, the Phase 15 validator, and dependency outage/recovery behavior.

## Known limitations retained for release

1. The representative roughly 12,000-document corpus is absent.
2. The target roughly 200-question reviewed evaluation set is absent.
3. No live hosted-provider quality/latency/cost acceptance was executed without credentials.
4. No production load, throughput, SLO, or cost benchmark is claimed.
5. Drift signals remain heuristic rather than statistical-significance evidence.
6. The serving rate limiter remains per-process rather than distributed/global.
7. `/metrics` remains intentionally unauthenticated for local Prometheus scraping; production deployment must restrict it at the network/edge layer.
8. Compose ports and development credentials remain local-development topology, not a production deployment blueprint.
9. Langfuse remains external/optional rather than locally composed.
10. Python dependency ranges are bounded but not a fully hash-locked supply-chain manifest.
11. Evaluation job state remains in-process/non-durable.
12. Qdrant recovery guidance remains reindex-first; environment-specific snapshot restore has not been proven here.
13. Upstream FastAPI/Starlette/httpx2/AnyIO and GitHub Actions Node-version deprecation warnings remain.
14. No ColPali/vision-table adapter exists in the current repository roadmap scope.

## Closure gate

This report intentionally does not declare Phase 15 closed. The remaining sequence is: validate this report-bearing PR head with all six CI jobs; mark PR #23 ready; merge with an expected-head SHA lock; require independent six-job `main` CI; update README/implementation-state/post-merge closure records; require final closure-head `main` CI; then create and verify the evidence-based `v0.1.0` release at that final main commit.
