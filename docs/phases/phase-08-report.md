# Phase 8 Report — Concurrent Hybrid Retrieval, Reciprocal Rank Fusion & Query Expansion

## Status

Phase 8 is complete, merged, and independently revalidated on `main`.

Final validated PR head: `e012de44d07e26059d7ccab7d040da2313be07dc`.
Final PR-head GitHub Actions run: `34717434998` — quality, integration/evidence/full regression, and dedicated local OCR all passed.
PR #8 merged as commit `b5d9b2d6d2b1f079ebe16f9a3119d35f83aa6cde`.
Post-merge `main` GitHub Actions run: `34717496000` — quality, integration with cleaning/chunking/dense/sparse/hybrid evidence and full regression, and dedicated installed-Tesseract OCR all passed.

The earlier implementation-acceptance head `4b6673e0aa4f63080d99730e8f4a87c9144cdc76` remains the source of the exact detailed test-count and fixture-timing evidence below; the final PR head and merge commit repeated the complete three-job gate without changing implementation behavior.

## Mission delivered

Phase 8 adds the project's central hybrid retrieval layer over the existing Phase 6 dense-Qdrant and Phase 7 BM25/BM25+ paths. It executes both branches concurrently, fuses canonical chunk rankings with deterministic Reciprocal Rank Fusion, preserves branch-specific evidence, applies equivalent metadata filters, and supports optional bounded query expansion behind an explicit provider boundary.

The implementation deliberately does not normalize or add dense cosine and BM25 scores. Their raw scores remain diagnostics; rank is the fusion currency.

## Architecture decisions

### Composition instead of retriever duplication

`HybridRetriever` consumes the existing rich `QdrantDenseIndex.search()` and `BM25SparseIndex.search()` contracts through small typed protocols. Phase 8 does not reimplement dense similarity, BM25 scoring, Qdrant lifecycle, sparse statistics, or their filter semantics.

A shared `HybridSearchFilter` is translated into the existing dense and sparse filter models with identical values for:

- domain;
- document ID;
- source-date lower/upper bounds;
- chunking-configuration fingerprint.

### Reciprocal Rank Fusion

`fuse_rrf()` uses explicit **1-based** source ranks and the formula:

```text
contribution = 1 / (rrf_k + rank)
```

The default smoothing constant is `rrf_k=60`. The reference branch candidate count is `20`; the final result count is independently configurable and defaults to `20`.

Each canonical `chunk_id` receives at most one contribution per branch. Duplicate occurrences inside one branch are reduced to the best-ranked occurrence. If dense and sparse return the same `chunk_id` with different canonical `Chunk` payloads, fusion fails with a typed `RetrievalError` instead of silently merging inconsistent provenance.

Stable final ordering uses fused RRF score descending, then best source rank, then canonical chunk ID. Fused `RetrievalResult` metadata and typed diagnostics retain:

- dense rank and raw dense score;
- sparse rank and raw sparse score;
- each branch's RRF contribution;
- final fused score/rank;
- inherited branch metadata.

### Concurrent execution and failure behavior

The production path starts dense and sparse tasks with `asyncio.create_task()` and awaits them together. External cancellation cancels both branches. A branch exception cancels its sibling, waits for cleanup, and surfaces a typed `RetrievalError`; exceptions are not swallowed.

A separate `search_sequential()` path executes the exact same branch calls sequentially for local diagnostic timing only. It is not a second production scoring path.

### Query expansion

Query expansion is disabled by default and controlled by versioned/fingerprinted configuration. `QueryExpansionProvider` is an async interface so future hosted expansion can remain optional. Phase 8 ships `DictionaryQueryExpansionProvider` as the deterministic CI/local baseline.

Expansion invariants:

- the normalized original query is always retained at the front of the retrieval query;
- expansion count is bounded;
- expansion character length is bounded;
- blank and duplicate expansions are removed case-insensitively;
- an expansion equal to the original query is dropped;
- generated expansions are returned in `HybridSearchResponse` and copied into fused-result metadata.

No hosted LLM expansion was implemented or claimed as validated in this phase.

### Configuration identity

`HybridRetrievalConfig` includes retriever version, branch top-k, final top-k, RRF constant, and expansion behavior. All behavior-affecting fields are included in `hybrid_config_fingerprint()` using the repository's existing deterministic fingerprint utility.

## Files changed

Production/configuration:

- `.github/workflows/ci.yml`
- `Makefile`
- `src/rageval/retrieval/hybrid/__init__.py`
- `src/rageval/retrieval/hybrid/models.py`
- `src/rageval/retrieval/hybrid/expansion.py`
- `src/rageval/retrieval/hybrid/rrf.py`
- `src/rageval/retrieval/hybrid/retriever.py`
- `scripts/hybrid_fixture_report.py`

Tests:

- `tests/unit/test_hybrid_retrieval.py`
- `tests/integration/test_hybrid_retrieval.py`
- `tests/unit/test_imports.py`

Documentation:

- `docs/plans/phase-08-hybrid-rrf-query-expansion.md`
- this report
- README and implementation-state handoff updates

## Required behavior tests

Unit tests cover:

- exact RRF arithmetic and explicit one-based rank handling;
- overlap across branches;
- stable tie ordering;
- duplicate-chunk suppression within one branch;
- dense-only and sparse-only/missing-branch results;
- same-ID/different-canonical-payload collision rejection;
- query-expansion count/length bounds, deduplication, and original-query retention;
- equivalent metadata-filter propagation to both branches;
- observable vocabulary expansion;
- async proof that dense and sparse start concurrently;
- sibling cancellation and typed error propagation when one branch fails;
- latency instrumentation without changing deterministic fused results.

Integration coverage starts from committed source fixtures and executes parser -> cleaner -> Phase 5 fixed-512 chunker -> Phase 6 real local Qdrant dense index + Phase 7 BM25+ sparse index -> concurrent Phase 8 fusion. It validates canonical chunk equality, document identity, source-element provenance, dense/sparse contribution diagnostics, filter propagation, hybrid config identity, and deterministic `turnover -> revenue` vocabulary expansion.

## Accepted verification evidence

Accepted implementation head:

`4b6673e0aa4f63080d99730e8f4a87c9144cdc76`

GitHub Actions run:

`34717256908`

Quality job:

- Python 3.11.16
- `ruff check .` — passed
- `ruff format --check .` — passed; **110 files already formatted**
- `mypy src` — passed; **no issues in 51 source files**
- `pytest -q tests/unit` — **103 passed in 1.27s**

Integration job:

- `docker compose config` — passed
- Qdrant `qdrant/qdrant:v1.10.1` and Redis `7.2-alpine` started successfully
- service readiness — passed
- `pytest -q tests/integration` — **26 passed, 1 skipped in 1.89s**
- sole ordinary-run skip — inherited local-OCR-only test because Tesseract is intentionally absent from the ordinary integration runner
- Phase 4 cleaning fixture evidence — passed
- Phase 5 chunking fixture ablation — passed
- Phase 6 real-Qdrant dense fixture evidence — passed
- Phase 7 sparse BM25 fixture evidence — passed
- Phase 8 hybrid RRF fixture evidence — passed
- package smoke — `rageval smoke: ok (development)`
- full `pytest -q` — **129 passed, 1 skipped in 2.84s**
- `docker compose down -v` — passed

Dedicated local OCR job:

- Tesseract **5.3.4** installed
- `pytest -q -m local_ocr tests/integration/test_local_ocr.py` — **1 passed in 0.68s**

## Machine-readable hybrid fixture evidence

Command:

```bash
python scripts/hybrid_fixture_report.py
```

Accepted-run fixture identity:

- corpus fingerprint: `cba5fea59f8d977e403fa66dd29bc7e282d040a183946b830652ab71af262927`
- source documents: 4
- indexed canonical chunks: 6
- chunk strategy: `fixed_512`
- dense provider: `local-hash`
- dense-provider evidence label: `local-hash-diagnostic-only`
- sparse index fingerprint for Phase 8's `phase8_ci_v1` snapshot: `6b21b395293770c63b7cc5b26e699b886c273890ddd6c9a7548829215d7ec5b6`
- hybrid config fingerprint: `37c45f72ab83fb04e27f4185e7f56456b5b6ea462adca6598093b7195a680c08`
- `rrf_k=60`
- branch top-k `20`

Deterministic lexical fixture query:

- query: `16.9`
- top chunk: `chk_0aa1f9408acc9a91748da01bf8ba93ee`
- dense rank: 1
- sparse rank: 1
- fused RRF score: `0.03278688524590164` (`2 / 61`)

Natural-language dense-path mechanics query:

- query: `revenue performance change across the reporting period`
- top chunk: `chk_0aa1f9408acc9a91748da01bf8ba93ee`
- this is **not** learned semantic retrieval-quality evidence; the dense provider is the deterministic local-hash mechanics adapter.

Vocabulary-mismatch query:

- original query: `quarterly turnover`
- deterministic expansion: `revenue`
- observable retrieval query: `quarterly turnover revenue`
- top chunk: `chk_0aa1f9408acc9a91748da01bf8ba93ee`
- sparse rank: 1

### Concurrent vs sequential timing

Three local fixture samples were recorded for each mode.

Concurrent total latencies, milliseconds:

- `6.488706000013167`
- `6.3819089999981315`
- `6.177913000001922`
- median: **6.3819089999981315 ms**

Sequential total latencies, milliseconds:

- `6.338067000001502`
- `6.221018999994499`
- `6.074943999990978`
- median: **6.221018999994499 ms**

Observed sequential/concurrent ratio: `0.974789675001057`.

Therefore this tiny local fixture does **not** support a claim that concurrency is faster; concurrent execution was slightly slower in this sample, consistent with overhead dominating very low-latency local branches. Concurrency correctness is established independently by deterministic async coordination tests. Any performance claim must be remeasured under representative provider/store latencies.

## Failure and repair history

Phase 8 was not accepted on the first working hybrid request:

1. Initial PR run `34716982365` proved the real-Qdrant + BM25 hybrid integration path, hybrid fixture report, all inherited fixture evidence, and real OCR. The cumulative suite then exposed three new unit cases using synthetic chunk IDs shorter than the existing canonical `Chunk.chunk_id` contract. The test fixtures were repaired to valid IDs; the contract was not relaxed. The same run also stopped quality at Ruff on import/line formatting.
2. Run `34717171620` passed Ruff lint and exposed canonical Ruff formatter changes in the hybrid report, RRF module, and hybrid unit tests. Ruff's exact layout was applied; no rule was suppressed.
3. Run `34717256908` reran all three jobs from the repaired head and passed quality, real-service integration/evidence/full regression, and installed-Tesseract OCR.
4. Final documentation head `e012de44d07e26059d7ccab7d040da2313be07dc` repeated all three jobs successfully in run `34717434998` before PR #8 left draft.
5. PR #8 merged as `b5d9b2d6d2b1f079ebe16f9a3119d35f83aa6cde`; independent merge-triggered `main` run `34717496000` again passed all three jobs.

No test, assertion, lint rule, formatter gate, strict type check, prior cleaning/chunking/dense/sparse evidence step, full regression test, or OCR validation was removed or weakened.

## Provider validation

Phase 8's deterministic acceptance path requires no new hosted provider. Query expansion uses the local dictionary adapter in tests/evidence. Hosted query expansion is intentionally unimplemented and therefore not claimed as tested.

Phase 6 hosted OpenAI embedding validation remains separately unrun because no credential-enabled CI run exists. Local-hash dense evidence continues to validate mechanics only, not learned semantic retrieval quality.

## Known limitations

- The hybrid acceptance corpus is 4 source documents / 6 canonical chunks, not the target roughly 12,000-document corpus. No production retrieval-quality or scale claim is made.
- The local-hash dense provider is not a learned semantic embedding model. The natural-language fixture query demonstrates mechanics only.
- No live OpenAI embedding result is introduced by Phase 8.
- Hosted/LLM query expansion is not implemented or live-tested; only the provider boundary and deterministic dictionary baseline are present.
- Query expansion currently augments one shared retrieval query for both branches. Representative evaluation may motivate branch-specific expansion later, but that would require an explicit versioned contract change.
- The tiny local timing fixture did not show a concurrency speedup. Realistic network/provider/store latency benchmarks are deferred until representative infrastructure/data are available.
- Phase 8 performs fusion only. Cross-encoder/Cohere reranking and multi-hop retrieval belong to Phase 9.
- No target-corpus retrieval benchmark, held-out context precision/recall, or RAG generation metric is claimed in this phase.
- GitHub Actions still emits a non-failing Node-action deprecation warning from current checkout/setup-python action versions.

## Canonical verification loop

```bash
ruff check .
ruff format --check .
mypy src
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
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated OCR validation remains:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

with Tesseract installed in the dedicated CI job.

## Phase 9 handoff

Phase 9 should consume Phase 8 fused candidates by canonical `chunk_id` and add reranking/multi-hop retrieval behind explicit provider interfaces. Reranking must retain dense rank/score, sparse rank/score, RRF contributions, hybrid config fingerprint, query-expansion diagnostics, and canonical provenance rather than overwriting them. Hosted Cohere Rerank or alternatives must remain an additional credential-dependent validation tier with a deterministic/local acceptance path.
