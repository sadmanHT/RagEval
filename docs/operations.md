# Operations Guide

## Scope and evidence boundary

This guide describes the Phase 14 local/container operational path. The composed API uses the deterministic `rageval.serving.fixture_runtime` so a clean machine can exercise HTTP serving, Redis caching, Qdrant/Redis readiness, Prometheus, Grafana, evaluation jobs, and security controls without hosted-provider credentials.

That runtime is **operational mechanics evidence only**. It is not represented as a production-quality retrieval/generation benchmark or as a generic production bootstrap for the absent roughly 12,000-document corpus and roughly 200-question held-out set.

## Clean local stack

Requirements:

- Docker with Compose v2;
- free local ports 3000, 6333, 6334, 6379, 8000, and 9090;
- Python 3.11 only when running host-side repository commands.

For local mechanics, Compose provides a deliberately obvious development API key if none is supplied. Override it outside disposable local development:

```bash
export RAGEVAL_SERVING_API_KEY='replace-this-local-key'
docker compose down -v --remove-orphans
docker compose up -d --build qdrant redis api prometheus grafana
python scripts/operational_smoke.py
```

Endpoints:

- API: `http://127.0.0.1:8000`
- readiness: `http://127.0.0.1:8000/health/ready`
- Prometheus metrics: `http://127.0.0.1:8000/metrics`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`

The same path is exposed as `make ops-up`, `make ops-smoke`, and `make ops-down`.

## Images and runtime hardening

`Dockerfile` has separate `runtime` and `test` targets. The runtime:

- uses a Python 3.11 slim base;
- installs the built project wheel rather than an editable source tree;
- runs as UID/GID 10001, not root;
- disables Python bytecode writes;
- exposes only port 8000;
- carries a readiness healthcheck;
- is run by Compose with all Linux capabilities dropped, `no-new-privileges`, a read-only root filesystem, and a small `/tmp` tmpfs.

The `test` target is separate from production runtime and installs development dependencies plus Tesseract. CI uses it to execute the entire cumulative repository suite against host-network Qdrant/Redis services.

Build locally with:

```bash
make docker-build
make docker-test-image
```

## Metrics and dashboards

Prometheus scrapes `/metrics` from the API. Metrics intentionally use bounded labels; request IDs, questions, chunk IDs, document IDs, job IDs, and exception strings are not metric labels.

Published metrics cover:

- HTTP request/error counts;
- HTTP latency histograms suitable for p50/p95/p99 calculation;
- retrieval, generation, pipeline, and API stage histograms;
- cache hit/miss/bypass counters;
- provider/pipeline failure counters;
- generation input/output token counters;
- estimated-cost counters when an adapter explicitly supplies cost metadata;
- evaluation job lifecycle, duration, and queue depth;
- dependency readiness;
- safe query-length distributions.

Grafana provisioning is committed under `ops/grafana/`. The default dashboard includes request rate, HTTP/stage p95 latency, cache ratio, provider failures, evaluation queue depth, and dependency readiness.

## Tracing and redaction

Tracing is disabled by default. `RAGEVAL_TRACING_PROVIDER=langfuse` selects the optional Langfuse adapter and requires:

```text
RAGEVAL_LANGFUSE_PUBLIC_KEY
RAGEVAL_LANGFUSE_SECRET_KEY
RAGEVAL_LANGFUSE_HOST
```

**Langfuse is external in Phase 14 and is not composed locally.** This avoids introducing another stateful application/database stack solely for deterministic acceptance.

Trace records include stable correlation IDs, query hash/length, branch/rank/RRF/rerank evidence, final chunk IDs, context/citation IDs, citation-validity state, provider/model identity, token counts, evaluation linkage, and stage latency. Retrieved document text is never serialized into the operational trace model. Raw query text is disabled by default and is included only when `RAGEVAL_OBSERVABILITY_INCLUDE_QUERY_TEXT=true` is deliberately configured.

Export failure logs retain exception class names only; raw downstream exception messages are not emitted.

## Drift hooks

`SafeAggregateDriftMonitor` retains bounded numeric samples only:

- query character lengths;
- embedding vector norms supplied through the public hook.

It reports `insufficient_data`, `stable`, or `potential_shift`. `potential_shift` is a configured heuristic signal, **not a claim of statistical significance**. The default minimum sample requirement is 30 and the default relative mean-shift threshold is 0.25.

## Security and abuse controls

The serving boundary preserves constant-time API-key validation and Phase 13 request-body limits. Phase 14 additionally provides:

- hashed fixed-window per-key request limiting;
- bounded security-sensitive request headers;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- `Cache-Control: no-store`;
- no cross-origin browser access by default;
- exact-origin CORS allowlists only; wildcard origins are rejected by settings validation.

The rate limiter is in-process. Multiple API workers/processes do **not** share a global quota in Phase 14. A future distributed limiter should use an external atomic store rather than pretending this local policy is global.

Dependency auditing uses `pip-audit`; production/operational surfaces are scanned with `detect-secrets`; Dependabot covers Python, Docker, and GitHub Actions dependencies.

## CI/CD semantics

Pull requests run checks that can genuinely block before merge:

- Ruff formatting/lint, strict mypy, and unit tests;
- deterministic integration tests using Qdrant/Redis;
- all inherited fixture evidence;
- PR-fast deterministic evaluation policy;
- Docker runtime/test builds;
- non-root runtime assertion;
- clean-volume complete Compose smoke;
- the entire repository test suite inside the test container;
- dependency-outage readiness/metric validation;
- dependency and secret scanning;
- dedicated installed-Tesseract OCR.

`.github/workflows/evaluation-full.yml` is schedule/manual only. It executes the largest currently available deterministic comparative matrix, applies the scheduled alert policy, and uploads run artifacts. Because it runs after merge or on explicit dispatch, its regression policy reports/alerts; it is not described as a pull-request blocker.

The real reviewed target evaluation set is still absent. Scheduled results therefore retain fixture-only labels and cannot be promoted into representative benchmark claims.

## Optional local model service

Compose includes an `ollama` service under the `local-model` profile:

```bash
docker compose --profile local-model up -d ollama
```

No Phase 14 acceptance result claims that the existing embedding/reranking/generation stack is wired to this service. It is an explicit optional infrastructure hook for a later local-provider integration, not a hidden fallback.

## Dependency outage drill

CI performs the Qdrant outage drill after the healthy operational smoke:

1. stop Qdrant;
2. require `/health/ready` to return HTTP 503;
3. require `rageval_dependency_ready{component="qdrant"}` to become `0`;
4. retain the API process so diagnostics remain available.

Redis degradation remains covered by the serving unit/integration health tests inherited from Phase 13.

## Recovery and data durability

### Qdrant — reindex first

The authoritative recoverable inputs are the governed source corpus, parser/cleaning/chunking configuration, canonical chunk identities, embedding/index configuration, and provider/version metadata. The preferred recovery path is to recreate the versioned Qdrant collection and reindex from those authoritative inputs. This avoids treating an opaque local Qdrant volume as the sole source of truth.

For deployments that choose Qdrant snapshots in addition to reindexability, snapshot creation/retention/restore must be tested against that deployment's Qdrant version and storage before it is treated as a recovery guarantee. Phase 14 does not claim such an environment-specific snapshot drill was executed.

### Redis — disposable cache

Redis stores query-cache entries only in the serving path. Cache identity includes index/retrieval/generation/model/prompt fingerprints. Redis data may be discarded and warmed again; it is not an authoritative recovery source.

### Evaluation artifacts

Comparative evaluation reports are immutable run artifacts carrying dataset/configuration/run identity. Scheduled CI uploads its artifacts with finite retention. A production deployment should copy approved reports/checkpoints to durable object storage or another controlled artifact store while preserving filenames, fingerprints, and checksums. The in-process `/eval/latest` and job table are not durable across API process restart.

### Prometheus and Grafana

Grafana datasource/dashboard definitions are source-controlled and reproducible. Local Prometheus/Grafana volumes are convenience state, not the sole authoritative copy of dashboards or evaluation results. Production monitoring retention/backup must be configured according to the chosen deployment platform.

## Full reproducibility commands

From a clean checkout:

```bash
pip install -e '.[dev]'
make verify
docker compose config
make integration
make evaluation-gate
make serving-report
make docker-build
make docker-test-image
make ops-smoke
make container-test
```

Then tear down disposable local state:

```bash
make ops-down
```

Hosted OpenAI/Cohere/Langfuse/W&B validation remains a separate credential-dependent tier. No blocked provider check is called passed.
