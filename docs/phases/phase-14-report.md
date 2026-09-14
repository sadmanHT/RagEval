# Phase 14 Report — Observability, Containers, CI/CD, Security, and Operational Hardening

## Status

**Implementation accepted on the pre-report PR head; final phase closure remains pending report-bearing exact-head CI, merge, and independent `main` validation.**

Phase 14 is implemented on pull request #14 (`phase-14-observability-ops`). The validated implementation head is `58ca0dc6c9888c2e55291aefffc7a0111e5e8cdb`. GitHub Actions run `34834352183` passed all five Phase 14 jobs: quality, integration, container, security, and dedicated local OCR.

This report intentionally distinguishes operational-mechanics evidence from representative product-quality evidence. The target roughly 12,000-document corpus and roughly 200-question reviewed held-out set are still absent. No OpenAI, Cohere, Langfuse, W&B, target-corpus quality, production-load, production-latency, production-cost, or statistically significant drift result is fabricated or claimed.

## Mission outcome

Phase 14 makes the existing Phase 13 async serving layer observable, container-reproducible, security-hardened, and CI-operable without replacing the canonical retrieval/generation/evaluation path.

Implemented scope includes:

- sanitized, Langfuse-compatible operational trace contracts and adapters;
- Prometheus metrics with deliberately bounded label cardinality;
- Grafana datasource/dashboard provisioning;
- safe aggregate query/embedding drift hooks;
- non-root multi-stage runtime/test Docker images;
- complete local Compose stack for API, Qdrant, Redis, Prometheus, and Grafana;
- optional local-model infrastructure hook without falsely claiming the RAG providers are wired to it;
- real PR-time container build, stack smoke, cumulative container test, and dependency-outage drill;
- deterministic PR-fast evaluation gating and separate scheduled/manual alert-only evaluation;
- dependency auditing, secret scanning, Dependabot, request abuse controls, safe CORS defaults, and response hardening;
- explicit Qdrant reindex, Redis cache, evaluation-artifact, Prometheus, and Grafana recovery/durability guidance.

## Architecture decisions

### Observability reuses the serving and evaluation boundaries

`OperationalTelemetry` is injected into the existing FastAPI application and bounded evaluation-job manager. Phase 14 does not create a second RAG pipeline or a parallel job system. Phase 13 authentication, cache identity, query schemas, streaming behavior, grounded citations, readiness semantics, and fixed evaluation workers remain canonical.

### Trace data is safe by construction

The trace model records identifiers and diagnostics rather than retrieved document bodies. Query traces include:

- stable correlation/trace identity;
- query SHA-256 and character length;
- optional raw query text only when explicitly configured;
- hop candidate chunk IDs;
- dense/sparse source ranks;
- RRF score and contributions;
- pre/post-rerank ranks and rerank score;
- final context chunk IDs and context token count;
- cited chunk IDs and citation-membership validity;
- provider/model identity and input/output token counts;
- retrieval/generation/pipeline/API latency.

Retrieved document text and assembled raw context are never serialized into the operational trace contract. `RAGEVAL_OBSERVABILITY_INCLUDE_QUERY_TEXT` defaults to `false`.

Langfuse is an optional external adapter in Phase 14, not another locally composed stateful stack. The deterministic acceptance path uses in-memory/null trace sinks; live Langfuse export was not run because credentials were not supplied.

### Metrics favor bounded cardinality

The Prometheus registry is application-scoped. Labels are restricted to finite route, method, status-class, stage, provider, operation, cache-outcome, dependency, and evaluation-state sets. Request IDs, job IDs, questions, chunk IDs, document IDs, and exception messages are not metric labels.

Published metrics cover HTTP request/error counts, HTTP and pipeline-stage histograms, cache outcomes, provider/pipeline failures, generation tokens, adapter-supplied estimated cost, evaluation lifecycle/duration/queue depth, dependency readiness, and query-length distribution. Histogram buckets support p50/p95/p99 calculations in Prometheus/Grafana without inventing percentile values in application code.

### Drift hooks retain numeric aggregates only

`SafeAggregateDriftMonitor` stores bounded query-length samples and embedding norms only. It returns `insufficient_data`, `stable`, or `potential_shift`. The default minimum sample requirement is 30. `potential_shift` is explicitly a configured heuristic, not a statistical-significance claim.

### Abuse controls remain intentionally local

The serving boundary keeps constant-time API-key comparison and request-body limits and adds:

- SHA-256 keyed fixed-window request limiting;
- bounded `X-API-Key`, `X-Request-ID`, and `Origin` header sizes;
- exact-origin CORS allowlists only;
- no browser CORS access by default;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- `Cache-Control: no-store`.

The rate limiter is **per process**. It is not represented as a distributed or multi-tenant global quota. A later production limiter should use an external atomic store.

### Container runtime and test image are separated

The runtime image uses `python:3.11.16-slim-bookworm`, builds and installs the project wheel, runs as UID/GID 10001, and carries a readiness healthcheck. Compose additionally drops all Linux capabilities, enables `no-new-privileges`, uses a read-only root filesystem, and gives only `/tmp` a small `noexec,nosuid` tmpfs.

The separate test target installs development dependencies plus Tesseract. This keeps OCR/build tooling out of the runtime image while allowing the entire repository suite to execute in the container acceptance path.

Python dependencies remain constrained by compatible version ranges rather than a fully hash-locked dependency file. Service/container base images used by the local operational stack are version-pinned; a complete Python lockfile is a future reproducibility improvement, not a claim made by this phase.

### Scheduled evaluation cannot be a PR blocker

PR CI runs a deterministic `pr_fast` evaluation gate before merge. `.github/workflows/evaluation-full.yml` is schedule/manual only, emits comparative evaluation plus `nightly` regression-alert artifacts, and retains them for 30 days. Because that workflow runs after merge or by explicit dispatch, it reports/alerts and is not described as a merge blocker.

The available dataset is still the three-record deterministic fixture, so both PR-fast and scheduled results retain fixture-only evidence labels.

### Recovery is based on authoritative inputs

Qdrant is **reindex-first**: the governed source corpus, parsing/cleaning/chunking configuration, canonical chunk IDs, embedding/index configuration, and provider/version metadata are the authoritative recovery inputs. Phase 14 does not claim an environment-specific Qdrant snapshot restore drill.

Redis contains query cache entries only and is disposable. Evaluation reports/checkpoints must be copied to controlled durable storage for production retention. Grafana dashboards/datasources are source-controlled; local Prometheus/Grafana volumes are convenience state rather than the sole source of truth.

## Files changed

Operational/source changes on the Phase 14 branch include:

- `.dockerignore`
- `.env.example`
- `.github/dependabot.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/evaluation-full.yml`
- `Dockerfile`
- `Makefile`
- `docker-compose.yml`
- `docs/operations.md`
- `docs/plans/phase-14-observability-docker-ci-cd-security.md`
- `ops/grafana/dashboards/rageval-operational.json`
- `ops/grafana/provisioning/dashboards/rageval.yml`
- `ops/grafana/provisioning/datasources/prometheus.yml`
- `ops/prometheus/prometheus.yml`
- `pyproject.toml`
- `scripts/evaluation_gate.py`
- `scripts/operational_smoke.py`
- `src/rageval/core/settings.py`
- `src/rageval/observability/__init__.py`
- `src/rageval/observability/drift.py`
- `src/rageval/observability/metrics.py`
- `src/rageval/observability/models.py`
- `src/rageval/observability/telemetry.py`
- `src/rageval/observability/tracing.py`
- `src/rageval/serving/app.py`
- `src/rageval/serving/fixture_runtime.py`
- `src/rageval/serving/jobs.py`
- `src/rageval/serving/security.py`
- `tests/unit/test_observability_phase14.py`
- `tests/unit/test_serving_observability_phase14.py`
- this report.

## Verification evidence

### Exact implementation head

Validated head: `58ca0dc6c9888c2e55291aefffc7a0111e5e8cdb`

GitHub Actions run: `34834352183`

All five jobs passed.

### Quality

- Ruff lint: passed.
- Ruff format check: **191 files already formatted**.
- strict mypy: **Success: no issues found in 90 source files**.
- unit suite: **181 passed**.

The preceding implementation head exposed one real strict-typing defect in `RequestGuardMiddleware`: a variable first inferred as `JSONResponse` was reused for a general `Response`. The repair made the downstream response type explicit without changing behavior; the exact repaired head then passed strict mypy.

### Host integration and cumulative regression

- ordinary integration: **31 passed, 1 skipped**;
- skip reason: local Tesseract binary intentionally absent from the ordinary integration job;
- full host cumulative suite: **212 passed, 1 skipped**;
- all inherited Phase 1–13 fixture evidence passed;
- dedicated installed-Tesseract job passed separately.

### PR-fast evaluation gate

The deterministic pre-merge evaluation gate passed with:

- evidence label: `phase14-fast-evaluation-fixture-gate-only`;
- fixture records: **3**;
- target dataset supplied: **false**;
- policy mode: PR-fast/blocking;
- `gate_failed=false`;
- `alert_triggered=false`.

These values validate regression-policy mechanics only. They are not representative RAG quality metrics.

### Container and operational acceptance

The container job passed every required operational stage from a clean CI context:

- `docker compose config` validation;
- clean runtime image build;
- clean test image build;
- runtime non-root assertion: **UID 10001**;
- clean-volume startup of API, Qdrant, Redis, Prometheus, and Grafana;
- authenticated operational HTTP smoke;
- entire repository suite inside the Tesseract-enabled test image;
- Qdrant outage readiness/metrics drill;
- clean teardown with volumes removed.

The containerized cumulative suite reported **213 passed** with Tesseract installed. This is consistent with the host cumulative result of 212 passed plus the one intentionally skipped OCR test.

The operational smoke emitted:

- `api_ready=true`;
- `authenticated_query=true`;
- cited chunk ID `chk_phase14_operational_fixture`;
- evaluation job state `succeeded`;
- `metrics_endpoint=true`;
- `prometheus_scrape_up=true`;
- Grafana database status `ok`;
- evidence label `phase14-container-operational-mechanics-only`.

This is deterministic fixture mechanics evidence, not production answer quality or load evidence.

### Dependency outage drill

CI stopped the live Qdrant container while keeping the API running. The API then returned HTTP 503 from `/health/ready` with:

- Qdrant: `degraded`;
- Redis: `ok`;
- generation provider: `ok`.

The Prometheus endpoint simultaneously exposed:

`rageval_dependency_ready{component="qdrant"} 0.0`

This validates useful dependency-health telemetry rather than merely proving that the API process exits on dependency failure.

### Security automation

The dedicated security job passed:

- `pip-audit` Python dependency audit;
- `detect-secrets` scanning of production and operational surfaces.

Dependabot configuration covers Python, Docker, and GitHub Actions dependencies.

Unit/API tests also cover missing/invalid auth, oversized body, security-sensitive header abuse, secret-bearing exception redaction, rate limiting, safe CORS defaults, response security headers, metrics label cardinality, and trace redaction.

## Reproducible commands

The canonical Phase 14 path is documented in `docs/operations.md`. Core commands are:

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
make ops-down
```

PR CI additionally runs dependency/secret scanning and the independently installed local-OCR job.

## Provider/live validation

Not run and not claimed:

- live OpenAI embeddings/generation;
- live Cohere reranking;
- live Langfuse export;
- live W&B tracking;
- any hosted judge using absent credentials.

Langfuse adapter behavior is covered deterministically through an injected fake client. Hosted-provider behavior already covered by prior mocked HTTP tests remains inherited; Phase 14 does not rename mocked behavior as live validation.

## Known limitations

1. The representative roughly 12,000-document corpus and roughly 200-question reviewed evaluation set are absent.
2. No production load, throughput, SLO, latency, or cost benchmark was run.
3. Drift hooks expose heuristic aggregate-shift signals only; no statistical significance is claimed.
4. The request limiter is in-process/per-process, not distributed or global across workers.
5. `/metrics` is intentionally unauthenticated for the local Prometheus scrape path; production deployment must restrict its network exposure at the edge/platform layer.
6. Compose exposes local API, Qdrant, Redis, Prometheus, and Grafana ports for reproducible development. Those bindings are not a production network-security topology.
7. Compose development credentials are deliberate local examples and must be overridden outside disposable local use.
8. Langfuse is external/optional; no Langfuse server/database is locally composed.
9. Python dependencies use bounded version ranges rather than a fully hash-pinned lockfile.
10. Evaluation job state and `/eval/latest` remain in-process/non-durable across API restart.
11. Qdrant snapshot restore was not environment-tested; recovery acceptance is reindex-first.
12. FastAPI/Starlette test execution currently emits upstream deprecation warnings around the TestClient/httpx2 transition and an AnyIO alias. They are warnings, not suppressed failures, and should be handled in dependency-maintenance work.
13. GitHub Actions currently reports that some pinned action majors target deprecated Node 20 and are forced onto Node 24 by the runner. This is an upstream workflow-maintenance warning, not an application test failure.

## Next-phase handoff

After this report-bearing head passes the same five CI jobs, PR #14 may leave draft. Merge must use the validated PR head. An independent merge-triggered `main` CI run must then pass all five jobs before Phase 14 is marked complete in README/implementation state.

After Phase 14, remaining engineering work is primarily production deployment/platform hardening and representative validation: distributed rate limiting/job durability if required by deployment topology, platform network/secrets policy, dependency locking/maintenance, production monitoring retention, real corpus/index bootstrap, real held-out evaluation, hosted-provider/live trace validation when credentials are deliberately supplied, and representative load/quality/cost measurement.