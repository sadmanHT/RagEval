# Phase 9 Report — Neural Reranking, Retrieval Service & Multi-hop Retrieval

## Status

Phase 9 implementation is accepted on draft PR #9 at head `48ac34e791893dca3c119925648738cc97599a7a` by GitHub Actions run `34718531754`. Quality, real-Qdrant/BM25 integration, all inherited cleaning/chunking/dense/sparse/hybrid evidence, the new reranked retrieval-service fixture, package smoke, full cumulative regression, and dedicated installed-Tesseract OCR are green.

PR merge and independent post-merge `main` validation remain required before final closure.

## Mission delivered

Phase 9 turns Phase 8 hybrid candidates into final retrieval context by adding provider-abstracted reranking and a bounded retrieval-service orchestrator. The service normalizes the user query, reuses Phase 8 hybrid retrieval, optionally executes traced second-hop retrieval, merges candidates by canonical `chunk_id`, reranks the merged set, and returns a default final top-5 context while preserving the original retrieval objects and provenance.

Multi-hop is disabled by default, so ordinary queries do not pay a second-hop cost unless explicitly enabled or rule-gated.

## Architecture decisions

### Reranker boundary

`RerankerProvider` exposes provider/model identity and one async scoring operation over query + candidate texts. Phase 9 provides:

- `DeterministicFakeReranker` for credential-free deterministic mechanics and CI acceptance;
- `CohereReranker` as the hosted reference adapter, using the Cohere v2 rerank endpoint through the repository's existing `httpx` dependency.

The deterministic fake is not a neural model and is not evidence of semantic reranking quality.

### Hosted retry, timeout, and parsing behavior

`CohereReranker` has bounded behavior:

- default model: `rerank-v3.5`;
- default timeout: 15 seconds;
- default attempts: 3, validated to the range 1–10;
- exponential backoff from 0.25 seconds;
- retryable HTTP statuses: 429, 500, 502, 503, 504;
- retry on network/timeout exceptions;
- strict JSON result parsing;
- rejection of missing scores/indexes, duplicate indexes, and out-of-range indexes.

Tests use `httpx.MockTransport` to validate the HTTP contract, rate-limit retry sequence, and timeout exhaustion. No live Cohere credential run is claimed.

### Reranking and provenance

`RerankingEngine` consumes Phase 8 `RetrievalResult` objects and returns the repository's existing `RerankResult` contract. It does not rebuild chunks or flatten retrieval diagnostics.

Each result preserves the original retrieval object and adds:

- rerank score;
- pre-rerank rank;
- post-rerank rank;
- provider-result index;
- reranker model;
- rerank configuration fingerprint.

Provider results are validated before use. Stable tie ordering is score descending, then original retrieval rank, then canonical chunk ID.

`RerankConfig` and provider/model identity are included in the deterministic rerank fingerprint.

### Retrieval-service orchestration

`RetrievalServiceConfig` defaults to:

- hybrid candidate top-k: 20;
- final context top-N: 5;
- multi-hop mode: `off`;
- max second-hop queries: 2;
- max merged candidates: 40.

`RetrievalService.search()` performs:

1. query normalization;
2. Phase 8 hybrid retrieval with the caller's filters intact;
3. multi-hop decision;
4. zero or more bounded second-hop hybrid searches using the same filters;
5. canonical ID merge with collision rejection;
6. reranking on the original normalized query;
7. final context plus hop/service/rerank diagnostics.

Merged retrieval metadata records which hop(s) and retrieval query/queries produced each retained candidate.

### Controlled multi-hop

`MultiHopMode` supports `off`, `always`, and `rule`.

- `off` is the default and guarantees no extra hop.
- `always` is an explicit opt-in mechanism.
- `rule` delegates to `MultiHopPlanner`.

The local `ReferenceAwareMultiHopPlanner` is intentionally conservative: it requires a relationship cue such as `how`, `why`, `affect`, `compare`, or similar, then extracts an explicit `Section`, `Clause`, `Appendix`, or `Schedule` reference from first-hop evidence. Derived queries are case-insensitively deduplicated and capped by configuration.

Every executed hop records its query, actual Phase 8 retrieval query, expansions, candidate chunk IDs, hybrid configuration fingerprint, and dense/sparse/total latency. These typed diagnostics are suitable for later evaluation and observability integration.

## Files changed

Production:

- `src/rageval/retrieval/rerank/__init__.py`
- `src/rageval/retrieval/rerank/models.py`
- `src/rageval/retrieval/rerank/providers.py`
- `src/rageval/retrieval/rerank/engine.py`
- `src/rageval/retrieval/service/__init__.py`
- `src/rageval/retrieval/service/models.py`
- `src/rageval/retrieval/service/multihop.py`
- `src/rageval/retrieval/service/orchestrator.py`

Tests/evidence:

- `tests/unit/test_reranking_service.py`
- `tests/integration/test_retrieval_service.py`
- `tests/unit/test_imports.py`
- `scripts/retrieval_service_fixture_report.py`

CI/task runner:

- `.github/workflows/ci.yml`
- `Makefile`

Documentation:

- `docs/plans/phase-09-reranking-multihop.md`
- this report
- `docs/implementation-state.md`
- `README.md`

## Required behavior tests

Unit coverage verifies:

- deterministic reranker ordering and preservation of original retrieval metadata;
- stable equal-score ordering by pre-rank then canonical ID;
- duplicate provider-index rejection;
- Cohere request/response parsing via mocked HTTP;
- exact bounded 429 retry/backoff behavior;
- timeout exhaustion after the configured attempt count;
- ordinary simple queries do not trigger rule-gated multi-hop;
- a first-hop chunk containing `See Section 9.2` derives a bounded second-hop query and recovers a non-adjacent chunk;
- default `off` mode stays single-hop even when a reference is present.

The real-service integration test starts from the committed source fixtures and executes parse -> clean -> Phase 5 fixed-512 chunking -> real local Qdrant dense + Phase 7 BM25+ -> Phase 8 RRF -> Phase 9 reranking. It proves a candidate can move from pre-rerank rank 6 to final rank 1 while preserving canonical source provenance and returns five final chunks. It also constrains a legal single-hop query to top-1 so the second legal chunk is absent, then uses an explicit bounded second hop to recover and rerank that non-adjacent chunk.

## Accepted verification evidence

Accepted implementation head:

`48ac34e791893dca3c119925648738cc97599a7a`

GitHub Actions run:

`34718531754`

Quality job:

- Python 3.11.16
- `ruff check .` — passed
- `ruff format --check .` — passed; **123 files already formatted**
- `mypy src` — passed; **no issues in 59 source files**
- `pytest -q tests/unit` — **114 passed in 1.44s**

Integration job:

- `docker compose config` — passed
- Qdrant and Redis startup/readiness — passed
- `pytest -q tests/integration` — **27 passed, 1 skipped in 2.31s**
- sole ordinary-run skip — inherited local-OCR-only test because Tesseract is intentionally absent from the ordinary integration runner
- Phase 4 cleaning fixture evidence — passed
- Phase 5 chunking fixture ablation — passed
- Phase 6 real-Qdrant dense fixture evidence — passed
- Phase 7 sparse BM25 fixture evidence — passed
- Phase 8 hybrid RRF fixture evidence — passed
- Phase 9 reranked retrieval-service fixture evidence — passed
- package smoke — `rageval smoke: ok (development)`
- full `pytest -q` — **141 passed, 1 skipped in 2.40s**
- Compose teardown — passed

Dedicated local OCR job:

- Tesseract **5.3.4** installed
- `pytest -q -m local_ocr tests/integration/test_local_ocr.py` — **1 passed in 0.98s**

## Machine-readable Phase 9 fixture evidence

Command:

```bash
python scripts/retrieval_service_fixture_report.py
```

Accepted-run fixture identity:

- source documents: 4
- indexed canonical chunks: 6
- chunk strategy: `fixed_512`
- dense provider: `local-hash`
- dense evidence label: `local-hash-diagnostic-only`
- sparse index fingerprint: `cb40c6bc98ba218751b4b926bce19148466b97f932a2fdfbc671ff1f4a8f8c43`
- service configuration fingerprint: `1fb23ec813c4ef27b156ac654620effed71f0c6154f995f50128c8bccdfd6856`
- rerank configuration fingerprint: `e1db77ff3b191e124eb9583de7eec473d0e6bf3e88d004fe1514d22ff09032f2`

### Top-5 rerank proof

- query source chunk: `chk_0aa1f9408acc9a91748da01bf8ba93ee`
- deliberately favored deterministic candidate: `chk_51e3471b7f313a1a164a57e03397043f`
- pre-rerank rank: **6**
- post-rerank rank: **1**
- final top-5 IDs:
  1. `chk_51e3471b7f313a1a164a57e03397043f`
  2. `chk_0aa1f9408acc9a91748da01bf8ba93ee`
  3. `chk_7d020b519dc5dec344a7d1213b6414a7`
  4. `chk_2b552c53fff02bba707df0f7e2e51db6`
  5. `chk_faa095f91126fa6e1a6bf03c400a19c7`

This proves rerank mechanics and identity preservation. It is not evidence that the deterministic fake improves retrieval quality.

### Two-hop mechanics proof

The legal fixture has two non-adjacent canonical chunks. The first-hop query is constrained to top-1 so the second chunk is absent. The explicit second-hop planner derives:

`7.2 Termination. Either party may terminate for material breach after a thirty-day cure period. Confidentiality obligations survive termination for three years.`

Evidence:

- first chunk: `chk_2b552c53fff02bba707df0f7e2e51db6`
- second-hop recovered chunk: `chk_1546d99922b41acf731a9877e524839e`
- hop count: 2
- final reranked order starts with the second-hop chunk, followed by the first-hop chunk
- both hop traces are retained.

The integration fixture deliberately injects this deterministic planner to isolate orchestration mechanics. The conservative rule planner is tested separately; no representative multi-hop recall improvement is claimed.

## Failure and repair history

Phase 9 was not accepted on its first CI attempt.

1. Initial PR run `34718290209` passed the Phase 9 real-service integration test, all inherited fixture evidence, and installed OCR. Quality stopped at one Ruff import-order issue. The Phase 9 fixture report then failed only while serializing evidence because it attempted a nonexistent convenience property `sparse.index_fingerprint` instead of the established Phase 7 contract `sparse.snapshot.index_fingerprint`.
2. The import order was changed to Ruff's canonical ordering and the report was corrected to use the existing Phase 7 snapshot contract. No runtime contract was relaxed and fingerprint evidence remained mandatory.
3. Run `34718444844` then passed the entire integration/evidence/smoke/full-regression path and installed OCR. Quality passed Ruff lint but Ruff formatter identified three Phase 9 files needing canonical layout.
4. Ruff's exact formatting was applied to the fixture report and the unit/integration tests. No assertion, rule, test, prior evidence gate, or behavior was removed.
5. Run `34718531754` repeated all three jobs from the repaired head and passed completely.

No test, assertion, lint/type gate, prior cleaning/chunking/dense/sparse/hybrid evidence step, smoke check, full regression test, or OCR validation was removed or weakened.

## Provider validation

- deterministic fake reranker — executed in unit/integration/evidence paths;
- Cohere hosted adapter request/response parsing — executed with mocked HTTP;
- Cohere rate-limit retry/backoff — executed with deterministic mocked 429 responses;
- Cohere timeout exhaustion — executed with deterministic mocked timeout errors;
- live Cohere reranking — **not run because no credential-enabled validation was available**;
- local neural cross-encoder — **not implemented**.

Therefore the repository has a complete offline mechanics/test path but does not have a complete offline *neural* reranking path. This limitation is explicit rather than being hidden behind the deterministic fake.

## Known limitations

- The acceptance corpus is 4 source documents / 6 canonical chunks, not the target roughly 12,000-document corpus.
- The deterministic fake reranker validates ordering, contracts, orchestration, and provenance only; it is not neural-quality evidence.
- The local-hash dense provider remains mechanics-only evidence.
- Live Cohere provider behavior was not exercised against the production service without credentials.
- No local neural cross-encoder adapter is present, so full offline neural reranking is unavailable.
- The reference-aware rule planner is conservative and heuristic. Its precision/recall must be measured on representative multi-hop questions before broader automatic use.
- The deterministic multi-hop integration fixture proves second-hop mechanics, not target-corpus quality improvement.
- No target-corpus context precision/recall, answer metric, or generation metric is claimed in Phase 9.
- GitHub Actions still emits a non-failing Node action deprecation warning from the current checkout/setup-python versions.

## Phase 10 handoff

Phase 10 should consume the final ordered `RerankResult` context set without discarding the nested Phase 8 retrieval diagnostics or canonical chunk/source provenance. Grounded generation should assemble structured context from these results, cite canonical chunk IDs for claims, refuse when context is insufficient, and keep provider invocation behind explicit interfaces. Any self-RAG/verification behavior must remain observable and evaluation-backed rather than silently rewriting the retrieval record.
