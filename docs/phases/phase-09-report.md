# Phase 9 Report — Neural Reranking, Retrieval Service & Multi-hop Retrieval

## Status

Phase 9 is complete, merged, and independently revalidated on `main`.

Final validated PR head: `28fa30cb6ee3997b02023c6cf2f54c07b8348f69`.
Final PR-head GitHub Actions run: `34718753817` — quality, integration/evidence/full regression, and dedicated local OCR all passed.
PR #9 merged as commit `0cf47f8dc7a2b3ae44c331cb287242c81284ce14`.
Post-merge `main` GitHub Actions run: `34718825100` — quality, integration with cleaning/chunking/dense/sparse/hybrid/reranked-service evidence and full regression, and dedicated installed-Tesseract OCR all passed.

The earlier implementation-acceptance head `48ac34e791893dca3c119925648738cc97599a7a` and run `34718531754` remain the source of the exact detailed test-count and fixture evidence below; the final PR head and merge commit repeated the complete three-job gate without changing implementation behavior.

## Mission delivered

Phase 9 turns Phase 8 hybrid candidates into final retrieval context by adding provider-abstracted reranking and a bounded retrieval-service orchestrator. The service normalizes the user query, reuses Phase 8 hybrid retrieval, optionally executes traced second-hop retrieval, merges candidates by canonical `chunk_id`, reranks the merged set, and returns a default final top-5 context while preserving the original retrieval objects and provenance.

Multi-hop is disabled by default, so ordinary queries do not pay a second-hop cost unless explicitly enabled or rule-gated.

## Architecture decisions

### Reranker boundary

`RerankerProvider` exposes provider/model identity and one async scoring operation over query + candidate texts. Phase 9 provides `DeterministicFakeReranker` for deterministic mechanics/CI acceptance and `CohereReranker` as the hosted reference adapter using the Cohere v2 rerank endpoint through the repository's existing `httpx` dependency.

The deterministic fake is not a neural model and is not evidence of semantic reranking quality.

### Hosted retry, timeout, and parsing behavior

`CohereReranker` has bounded behavior: default model `rerank-v3.5`, 15-second timeout, 3 attempts by default (validated to 1–10), exponential backoff from 0.25 seconds, retryable statuses 429/500/502/503/504, network/timeout retries, strict JSON parsing, and rejection of missing/duplicate/out-of-range result indexes.

Tests use `httpx.MockTransport` to validate request/response parsing, rate-limit retry sequence, and timeout exhaustion. No live Cohere credential run is claimed.

### Reranking and provenance

`RerankingEngine` consumes Phase 8 `RetrievalResult` objects and returns the repository's existing `RerankResult` contract. It does not rebuild chunks or flatten retrieval diagnostics. Each result preserves the original retrieval object and adds rerank score, pre-rerank rank, post-rerank rank, provider-result index, reranker model, and rerank configuration fingerprint. Stable tie ordering is score descending, then original retrieval rank, then canonical chunk ID.

### Retrieval-service orchestration

`RetrievalServiceConfig` defaults to hybrid candidate top-k 20, final context top-N 5, multi-hop `off`, max second-hop queries 2, and max merged candidates 40.

`RetrievalService.search()` performs query normalization, Phase 8 hybrid retrieval with caller filters intact, optional bounded second-hop searches with the same filters, canonical ID merge with collision rejection, reranking on the original normalized query, and final context plus hop/service/rerank diagnostics. Merged retrieval metadata records which hop(s) and retrieval queries produced each retained candidate.

### Controlled multi-hop

`MultiHopMode` supports `off`, `always`, and `rule`. `off` is the default. `always` is explicit opt-in. `rule` delegates to `MultiHopPlanner`. The local `ReferenceAwareMultiHopPlanner` is conservative: it requires a relationship cue and extracts an explicit `Section`, `Clause`, `Appendix`, or `Schedule` reference from first-hop evidence. Derived queries are deduplicated and capped.

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

Tests/evidence and CI:

- `tests/unit/test_reranking_service.py`
- `tests/integration/test_retrieval_service.py`
- `tests/unit/test_imports.py`
- `scripts/retrieval_service_fixture_report.py`
- `.github/workflows/ci.yml`
- `Makefile`

Documentation:

- `docs/plans/phase-09-reranking-multihop.md`
- this report
- `docs/implementation-state.md`
- `README.md`

## Required behavior tests

Unit coverage verifies deterministic reranker ordering and provenance preservation, stable equal-score ordering, duplicate provider-index rejection, Cohere parsing via mocked HTTP, bounded 429 backoff, timeout exhaustion, simple-query non-triggering, reference-derived second-hop recovery, and default-off single-hop behavior.

The real-service integration test executes parse -> clean -> fixed-512 chunking -> real local Qdrant dense + BM25+ -> Phase 8 RRF -> Phase 9 reranking. It proves a candidate can move from pre-rerank rank 6 to final rank 1 while retaining canonical source provenance and returns five final chunks. It also constrains a legal single-hop query to top-1 so a second legal chunk is absent, then uses an explicit bounded second hop to recover and rerank that non-adjacent chunk.

## Accepted verification evidence

Accepted implementation head: `48ac34e791893dca3c119925648738cc97599a7a`

Accepted implementation run: `34718531754`

Quality:

- Python 3.11.16
- Ruff — passed
- Ruff formatter — passed; **123 files already formatted**
- strict mypy — **no issues in 59 source files**
- unit suite — **114 passed in 1.44s**

Integration:

- Compose configuration/startup/readiness — passed
- ordinary integration — **27 passed, 1 skipped in 2.31s**
- sole ordinary-run skip — inherited local-OCR-only test because Tesseract is intentionally absent from that runner
- cleaning/chunking/dense/sparse/hybrid evidence — all passed
- Phase 9 reranked retrieval-service fixture — passed
- package smoke — `rageval smoke: ok (development)`
- full cumulative suite — **141 passed, 1 skipped in 2.40s**
- Compose teardown — passed

Dedicated OCR:

- Tesseract **5.3.4** installed
- local OCR fixture — **1 passed in 0.98s**

Final PR-head run `34718753817` repeated all three jobs successfully on head `28fa30cb6ee3997b02023c6cf2f54c07b8348f69`.
Post-merge run `34718825100` independently repeated all three jobs successfully on merge commit `0cf47f8dc7a2b3ae44c331cb287242c81284ce14`.

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

This proves rerank mechanics and identity preservation, not retrieval-quality improvement by the deterministic fake.

### Two-hop mechanics proof

The legal fixture has two non-adjacent canonical chunks. The first-hop query is constrained to top-1 so the second chunk is absent. The explicit second-hop planner derives:

`7.2 Termination. Either party may terminate for material breach after a thirty-day cure period. Confidentiality obligations survive termination for three years.`

Evidence:

- first chunk: `chk_2b552c53fff02bba707df0f7e2e51db6`
- second-hop recovered chunk: `chk_1546d99922b41acf731a9877e524839e`
- hop count: 2
- final reranked order starts with the second-hop chunk, followed by the first-hop chunk
- both hop traces are retained.

The integration fixture injects this deterministic planner to isolate orchestration mechanics. The conservative rule planner is tested separately; no representative multi-hop recall improvement is claimed.

## Failure and repair history

1. Initial PR run `34718290209` passed the Phase 9 real-service integration test, all inherited fixture evidence, and installed OCR. Quality stopped at one Ruff import-order issue. The Phase 9 fixture report then failed while serializing evidence because it used a nonexistent `sparse.index_fingerprint` convenience property instead of the established Phase 7 `sparse.snapshot.index_fingerprint` contract.
2. The import order was made canonical and the report was corrected to the existing Phase 7 snapshot contract. No runtime contract was relaxed and fingerprint evidence remained mandatory.
3. Run `34718444844` passed the entire integration/evidence/smoke/full-regression path and installed OCR. Quality passed Ruff lint but Ruff formatter identified three Phase 9 files needing canonical layout.
4. Ruff's exact formatting was applied. No assertion, rule, test, prior evidence gate, or behavior was removed.
5. Run `34718531754` passed completely. Final docs-head run `34718753817` and independent merge run `34718825100` repeated the complete gate.

No test, assertion, lint/type gate, prior cleaning/chunking/dense/sparse/hybrid evidence step, smoke check, full regression test, or OCR validation was removed or weakened.

## Provider validation

- deterministic fake reranker — executed in unit/integration/evidence paths;
- Cohere hosted adapter parsing — executed with mocked HTTP;
- Cohere 429 retry/backoff — executed with deterministic mocked responses;
- Cohere timeout exhaustion — executed with deterministic mocked timeout errors;
- live Cohere reranking — **not run because no credential-enabled validation was available**;
- local neural cross-encoder — **not implemented**.

The repository therefore has a complete offline mechanics/test path but not a complete offline *neural* reranking path.

## Known limitations

- Acceptance corpus is 4 documents / 6 chunks, not the target roughly 12,000-document corpus.
- Deterministic fake reranker validates mechanics, not neural quality.
- Local-hash dense provider remains mechanics-only evidence.
- Live Cohere behavior was not exercised against the hosted service.
- No local neural cross-encoder adapter is present.
- The reference-aware rule planner is conservative and heuristic; its precision/recall needs representative evaluation before broader automatic use.
- The deterministic multi-hop fixture proves mechanics, not target-corpus quality improvement.
- No target-corpus retrieval or generation metric is claimed.
- GitHub Actions still emits a non-failing Node action deprecation warning from current checkout/setup-python versions.

## Phase 10 handoff

Phase 10 should consume the final ordered `RerankResult` context set without discarding nested Phase 8 retrieval diagnostics, Phase 9 hop/rerank diagnostics, or canonical chunk/source provenance. Grounded generation should assemble structured context from these results, cite canonical chunk IDs for claims, refuse when context is insufficient, and keep provider invocation behind explicit interfaces. Any self-RAG/verification behavior must remain observable and evaluation-backed rather than silently rewriting the retrieval record.
