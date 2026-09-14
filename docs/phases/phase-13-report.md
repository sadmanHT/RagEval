# Phase 13 Report — FastAPI Serving, Authentication, Caching, Streaming & Evaluation Jobs

## Status

Phase 13 implementation is accepted on branch `phase-13-fastapi-serving` at implementation head `2d9b0100c080f8e9784a457b1a80f5031b11cc31` by GitHub Actions run `34828986926`.

That run passed all three CI jobs: quality, service-backed integration/full regression, and dedicated installed-Tesseract OCR. This report is being added after that accepted implementation run; the report-bearing PR head must itself pass the same cumulative CI before PR #13 is marked ready or merged.

The representative roughly 12,000-document corpus and roughly 200-question held-out evaluation set are still not present. No representative retrieval/generation/evaluation quality, latency, cost, or production-load result is claimed from Phase 13. The serving fixture is explicitly mechanics/grounding/traceability evidence over the committed local corpus.

## Mission delivered

Phase 13 exposes the existing retrieval/generation/evaluation stack through a typed async FastAPI boundary without replacing the canonical Phase 9–12 services.

Delivered behavior includes:

- typed FastAPI application construction with Pydantic request/response contracts and generated OpenAPI;
- authenticated `POST /query` with optional domain, metadata filters, `top_k`, cache and streaming options;
- `GET /health/live` and `GET /health/ready`, with dependency-aware degraded readiness;
- authenticated `POST /eval/run`, `GET /eval/jobs/{job_id}`, and `GET /eval/latest`;
- constant-time API-key comparison with distinct missing-key `401` and invalid-key `403` behavior;
- request IDs, request-body size enforcement, bounded query timeouts, bounded query concurrency, and generic safe error responses;
- Redis response caching whose identity includes normalized query/options/filters plus index, retrieval-config, generation-config, model, and prompt identity;
- transport-level NDJSON streaming that emits answer deltas and a final structured response retaining citations;
- client-disconnect cancellation for in-flight streaming queries;
- a bounded fixed-worker evaluation queue rather than unconstrained per-request background tasks;
- health checks for Qdrant, Redis, and configured provider checks;
- sanitized unexpected-error logging for normal requests, streaming failures, and evaluation workers so downstream exception messages cannot leak credential material;
- real local Qdrant + Redis serving evidence over the committed fixture corpus with deterministic embedding, reranking, generation, and evaluation providers.

## Architecture decisions

### Reuse the canonical Phase 9–12 pipeline

`/query` delegates to the existing `GroundedGenerationService`, which in turn consumes the established retrieval service and grounded-generation contracts. Phase 13 does not introduce a second retrieval/generation implementation. Request-scoped `top_k` is threaded through the existing retrieval/generation boundary so API behavior remains inside the canonical service path.

### Cache grounded internal results, not transport envelopes

The cache stores the internal `GroundedGenerationResponse`. Request IDs and API timing are rebuilt per HTTP request, so a cache hit cannot replay another caller's request identifier or stale HTTP-envelope metadata.

Cache keys include behavior-affecting request fields plus:

- index fingerprint;
- retrieval-service configuration fingerprint;
- generation configuration fingerprint;
- model version;
- prompt version.

The permanent serving fixture proves a changed index fingerprint causes a miss and executes grounded generation again.

### Streaming is transport streaming

The current provider abstraction returns a completed grounded answer, so Phase 13 does not falsely claim provider-native token streaming. The API offers optional NDJSON transport streaming over the completed answer, then emits one final structured event containing the same citation/refusal/diagnostic contract as non-streaming mode.

Disconnect handling cancels an in-flight query task when the request disconnects before completion. Unexpected streaming failures emit only a structured generic error event and log the exception class name, not the exception message.

### Concurrency is bounded at both expensive boundaries

Interactive queries use a configured semaphore and request timeout. Evaluation jobs use a fixed number of worker tasks plus a bounded queue. A full queue returns `429` rather than spawning unlimited background work.

The evaluation queue is intentionally in-process for this phase. It is suitable for bounded local/single-process execution but is not a durable distributed job system.

### Health separates liveness from readiness

`/health/live` verifies the process boundary only. `/health/ready` executes registered async dependency checks and returns `503` with component status when a required dependency is degraded. Redis is automatically included when a cache is configured; Qdrant/provider checks are injected by application assembly.

### Errors and logs fail closed around secrets

Validation and internal errors return fixed safe envelopes. API keys and request bodies are not logged. Generic request, streaming, and evaluation-worker exception paths intentionally retain only request/job correlation and exception class names; they do not log arbitrary downstream exception strings or tracebacks that may contain provider credentials.

## Files changed

Phase 13 implementation changes include:

- `.env.example`
- `.github/workflows/ci.yml`
- `Makefile`
- `docs/plans/phase-13-fastapi-auth-cache-streaming-jobs.md`
- `docs/phases/phase-13-report.md`
- `pyproject.toml`
- `scripts/serving_fixture_report.py`
- `src/rageval/core/settings.py`
- `src/rageval/generation/service.py`
- `src/rageval/retrieval/service/orchestrator.py`
- `src/rageval/serving/__init__.py`
- `src/rageval/serving/app.py`
- `src/rageval/serving/cache.py`
- `src/rageval/serving/health.py`
- `src/rageval/serving/jobs.py`
- `src/rageval/serving/models.py`
- `tests/integration/test_serving_phase13.py`
- `tests/unit/test_serving_api_phase13.py`
- `tests/unit/test_serving_cache_stream_phase13.py`
- `tests/unit/test_serving_jobs_health_phase13.py`

## Behavioral test coverage

Phase 13 tests cover:

- OpenAPI generation and required endpoint presence;
- auth success, missing-key `401`, and invalid-key `403`;
- request-ID propagation;
- request body size rejection;
- request-scoped `top_k` and domain-filter propagation into the canonical query service;
- query concurrency bounds;
- Redis cache hit behavior;
- cache-key invalidation for index/prompt/filter changes;
- final streaming citations;
- deterministic cancellation of an actually in-flight stream on disconnect;
- sanitized unexpected streaming failure;
- evaluation create/status/latest lifecycle;
- configured evaluation-worker concurrency;
- sanitized evaluation-worker failure;
- Qdrant/Redis readiness degradation;
- secret-bearing downstream exceptions absent from HTTP responses and captured logs;
- real local Qdrant + Redis endpoint integration over committed source fixtures;
- every inherited Phase 4–12 evidence command and the full cumulative regression suite.

## Accepted verification evidence

Accepted implementation head:

`2d9b0100c080f8e9784a457b1a80f5031b11cc31`

Accepted GitHub Actions run:

`34828986926`

Results from that exact implementation head:

| Verification | Result |
| --- | --- |
| `ruff check .` | passed |
| `ruff format --check .` | passed |
| strict `mypy` | passed on 82 source files |
| `pytest -q tests/unit` | 173 passed |
| `docker compose config` | passed |
| local Qdrant + Redis startup/readiness | passed |
| `pytest -q tests/integration` | 31 passed, 1 intentional OCR skip |
| inherited cleaning/chunking/dense/sparse/hybrid/retrieval/generation/evaluation/ablation fixture evidence | passed |
| `python scripts/serving_fixture_report.py` | passed |
| `python -m rageval.smoke` | passed |
| full `pytest -q` | 204 passed, 1 intentional OCR skip; 2 dependency deprecation warnings |
| dedicated installed-Tesseract OCR | 1 passed |

The ordinary integration/full run intentionally skips `tests/integration/test_local_ocr.py` when the Tesseract executable is absent from that job. The dedicated OCR job installs Tesseract 5.3.4 and passed the test independently, so OCR remains covered rather than silently disabled.

The two full-suite warnings are current FastAPI/Starlette test-client dependency deprecations (`httpx`/`httpx2` and AnyIO `BlockingPortal` alias usage); they do not change the accepted behavior but should be revisited during dependency maintenance.

## Phase 13 machine-readable fixture evidence

`python scripts/serving_fixture_report.py` uses the committed source fixtures, real local Qdrant, real local Redis, the canonical retrieval/generation services, and deterministic providers. Accepted run `34828986926` reported:

```json
{
  "authenticated_query": true,
  "cache_hit": true,
  "cache_invalidated_after_index_change": true,
  "canonical_chunks": 6,
  "evaluation_job_status": "succeeded",
  "evidence_label": "phase13-serving-fixture-mechanics-only",
  "qdrant_ready": true,
  "redis_ready": true,
  "schema_version": "1.0",
  "source_documents": 4,
  "stream_final_citations": [
    "chk_0aa1f9408acc9a91748da01bf8ba93ee"
  ]
}
```

The generated evaluation job ID is deliberately omitted from this report because it is per-run ephemeral identity, not stable evidence.

This fixture establishes that a local ASGI client can authenticate, query the real local fixture index/cache path, receive a non-refusal grounded cited answer, hit Redis on an identical request, miss after an index-identity change, retain citations in the final streaming event, trigger/check an evaluation job, and observe dependency readiness. It does not establish hosted-provider quality or production scale.

## Failure and repair history

The implementation was not declared complete after the first successful endpoint path. CI exposed several issues that were repaired without deleting tests or weakening assertions:

1. Ruff identified mechanical formatting/assertion layout changes; source was formatted rather than relaxing lint.
2. PyMuPDF emitted a layout recommendation before machine-readable JSON evidence; the evidence script suppresses that advisory so stdout remains deterministic JSON rather than weakening evidence parsing.
3. Strict mypy identified Starlette middleware typing incompatibility; middleware construction now uses the proper generic ASGI application type.
4. The serving evidence initially observed a pre-existing Redis key written by the integration test; the script now explicitly clears both baseline and changed-index identities before cache assertions.
5. The first disconnect unit test could cancel the spawned task before its coroutine had started, so it could not prove in-flight cancellation. The test now synchronizes on a start event before reporting disconnect.
6. The first evaluation-concurrency fixture omitted Phase 12's required `metric_slices`, causing fixture validation failure rather than a worker-concurrency failure. The fixture now constructs a valid `ConfigurationRun`.
7. Security review found generic `logger.exception` paths could serialize arbitrary downstream exception messages. Request, stream, and evaluation-worker failures now log only safe correlation metadata and exception class names, with explicit secret-bearing regression tests.

The final accepted implementation head then passed the entire cumulative CI suite.

## Provider and representative-data validation

### Executed

- real local Qdrant integration: passed;
- real local Redis cache/readiness integration: passed;
- deterministic local-hash embedding mechanics: passed as inherited/local fixture evidence;
- deterministic reranker mechanics: passed;
- deterministic grounded-generation mechanics: passed;
- deterministic evaluation-job mechanics: passed;
- installed local Tesseract OCR: passed.

### Not claimed / blocked by unavailable inputs

- live OpenAI embedding validation: not run without credentials;
- live Cohere reranking validation: not run without credentials;
- live OpenAI generation validation: not run without credentials;
- live LLM judge/RAGAS semantic evaluation: not run without the relevant provider/runtime setup;
- representative roughly 12,000-document serving/load benchmark: not run because the corpus is absent;
- representative roughly 200-question end-to-end evaluation: not run because the reviewed held-out set is absent;
- production latency/cost/load/SLO numbers: not fabricated from the tiny fixture.

## Known limitations

1. Streaming is transport-level chunking of a completed grounded response, not provider-native token streaming.
2. Evaluation jobs and latest-job state are in process and are lost on process restart; no durable/distributed queue is claimed.
3. The query semaphore bounds concurrency within one application process. Cross-process/global rate limiting is not part of Phase 13.
4. Cache invalidation is identity based. Deployment/application assembly must provide current index/config/model/prompt fingerprints when those artifacts change.
5. Readiness checks cover configured dependencies, but this phase does not introduce circuit breakers, multi-region failover, backup/restore, or disaster-recovery guarantees.
6. There is no production load test, multi-tenancy model, per-principal quota/rate limiting, or external secrets-manager integration in this phase.
7. Safe generic error logging intentionally omits arbitrary exception messages/tracebacks. Later observability should add sanitized correlated tracing rather than reintroducing secret-bearing raw exception output.
8. The current FastAPI/Starlette test stack emits two deprecation warnings that should be handled in a dependency-maintenance pass.

These limitations are why the repository continues to describe the architecture as production-oriented rather than claiming demonstrated production readiness.

## Reproducible commands

From a clean development checkout with the project development dependencies installed:

```bash
ruff check .
ruff format --check .
mypy .
pytest -q tests/unit
docker compose config
docker compose up -d qdrant redis
python scripts/wait_for_services.py
pytest -q tests/integration
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
python scripts/dense_fixture_report.py
python scripts/sparse_fixture_report.py
python scripts/hybrid_fixture_report.py
python scripts/retrieval_service_fixture_report.py
python scripts/generation_fixture_report.py
python scripts/evaluation_fixture_report.py
python scripts/evaluation_ablation_fixture_report.py
python scripts/serving_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

The Phase 13 evidence command is also exposed as:

```bash
make serving-report
```

The dedicated OCR gate additionally installs Tesseract and runs:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

## Exact handoff state

At the accepted implementation head, the repository has a tested async serving boundary over the canonical RAG and evaluation stack, with authentication, correctness-scoped caching, structured streaming, dependency readiness, bounded interactive/evaluation concurrency, request correlation, and secret-safe generic failures.

The next engineering handoff is observability and scheduled evaluation/deployment hardening: add correlated traces/metrics/cost accounting and evaluation-trend surfaces without duplicating the existing experiment tracker, define scheduling semantics that do not misrepresent post-merge jobs as PR blockers, and preserve the same deterministic-vs-live evidence separation. Representative validation remains blocked until the real reviewed evaluation set, representative corpus/index, and any required live-provider credentials are supplied.

Before Phase 13 can be declared closed, the new report-bearing PR head must pass cumulative CI, PR #13 must be merged, and the merge-triggered `main` CI must pass independently.
