# Phase 6 Report — Embeddings, Qdrant Indexing & Dense Retrieval

## Status

Phase 6 implementation is accepted on PR #6 implementation head
`dbb48da4b42a0d3a041c1bfc919fbf43f6bb2aa8` by GitHub Actions run `34709254448`.
The code-level acceptance gates are green. This report is part of the final documentation head, so
PR merge and post-merge `main` validation are intentionally recorded after this report is committed.

## Mission delivered

Phase 6 adds a reproducible dense-retrieval boundary over canonical Phase 5 chunks. The system can
embed chunks behind a provider abstraction, create and validate a versioned Qdrant collection,
idempotently index reconstructable chunk payloads, filter and search them, replace/delete document
contents, detect index inconsistencies, and reconstruct the existing canonical `RetrievalResult`
contract from real local Qdrant results.

No sparse retrieval, fusion, reranking, generation, or evaluation-runner functionality is included;
those remain later-phase scope.

## Architecture decisions

### Embedding providers

- The existing `EmbeddingProvider` protocol remains source-compatible for Phase 5 semantic
  chunking. Phase 6 introduces `DenseEmbeddingProvider`, extending that boundary with explicit
  `model` and `dimension` information required to validate vector-index schemas.
- `OpenAIEmbeddingProvider` uses the hosted reference model `text-embedding-3-large` and a 3072
  dimensional default. It supports explicit requested dimensions, preserves input order through
  response-index validation, validates numeric vector length, and wraps HTTP/provider failures in
  the project `ProviderError`.
- `LocalHashDenseEmbeddingProvider` reuses the deterministic Phase 5 local hash implementation. It
  is an offline mechanics/integration provider only. Its successful fixture results are not a
  learned semantic-quality benchmark.
- No embedding API fine-tuning capability is claimed or implemented.

### Qdrant collection identity and schema

- Collections use a versioned name: `<collection_base>__<collection_version>`.
- Phase 6 uses one unnamed cosine vector with explicit dimensional validation.
- HNSW construction parameters (`m`, `ef_construct`) and search parameters (`hnsw_ef`, exact mode)
  are configuration-owned rather than hard-coded at call sites.
- Existing collection vector size and distance are validated before use. A mismatch raises an
  explicit `IndexingError` directing the operator to bump the collection version or rebuild; stale
  schemas are never silently reused.
- Payload indexes are created for `domain`, `document_id`, `source_date_ordinal`, and
  `chunking_config_fingerprint`.

### Point identity, payloads, and idempotency

- Canonical project chunk IDs remain unchanged. Qdrant point IDs are deterministic UUIDv5 values
  derived from each canonical `chunk_id`, producing stable reingestion identity while retaining the
  original `chk_...` identifier in payloads.
- Every point payload contains the full serialized canonical `Chunk` plus document/source metadata,
  chunking fingerprint, embedding provider/model/dimension, and collection version. Source dates are
  stored both as ISO text and ordinal values when available.
- Repeating the same document upsert therefore replaces the same point IDs instead of creating
  duplicates.
- `replace_document` is deliberately implemented as delete-then-upsert. It is not claimed to be a
  transactional multi-operation replacement; callers that require cross-operation atomicity need a
  later generation/version swap strategy.

### Dense search

- Search supports top-k plus domain, source-date range, document ID, and chunking-config filters.
- Query embedding, Qdrant search, and total latency are measured independently in the response.
- Results reconstruct the canonical `Chunk` and existing project `RetrievalResult` contract.
- Equal-score output is made stable with `chunk_id` as the secondary ordering key.
- Query latency values emitted by fixture CI prove instrumentation only; they are not load-test or
  production performance benchmarks.

## Files changed

Production/configuration changes:
- `.env.example`
- `.github/workflows/ci.yml`
- `Makefile`
- `pyproject.toml`
- `scripts/dense_fixture_report.py`
- `src/rageval/core/settings.py`
- `src/rageval/retrieval/dense/__init__.py`
- `src/rageval/retrieval/dense/models.py`
- `src/rageval/retrieval/dense/providers.py`
- `src/rageval/retrieval/dense/qdrant.py`
- `src/rageval/testing/fakes.py`

Tests:
- `tests/integration/test_dense_qdrant.py`
- `tests/unit/test_dense_retrieval.py`
- `tests/unit/test_imports.py`
- `tests/unit/test_settings.py`

Documentation/handoff changes include this report, the Phase 6 implementation plan already present
on `main`, implementation-state/README reconciliation, and removal of temporary Phase 6 branch
marker/note files that were not intended as permanent project documentation.

## Deterministic and real-service tests

Unit coverage includes:
- versioned collection naming;
- malformed date-range validation;
- deterministic Qdrant-compatible point IDs;
- provider/index dimension mismatch rejection;
- deterministic local embedding vector dimensions;
- mocked OpenAI request model/input/dimension shape;
- OpenAI response reordering by returned index;
- wrong OpenAI vector dimension rejection;
- hosted HTTP failure wrapping;
- settings/import regressions.

Real local Qdrant integration coverage includes:
- collection creation and payload-index setup;
- idempotent repeated document ingestion with no duplicate points;
- exact expected-versus-indexed document consistency;
- deterministic relevance sanity using an exact source chunk as query;
- domain filter;
- source-date filter;
- document filter;
- delete/reindex document lifecycle;
- stale collection vector-dimension rejection;
- unavailable-Qdrant failure handling;
- end-to-end fixture flow: manifest -> parser -> cleaner -> Phase 5 chunker -> local embedding ->
  real Qdrant -> canonical dense retrieval result with chunk ID/config/source-element/page provenance.

## Accepted verification evidence

Accepted implementation head:
`dbb48da4b42a0d3a041c1bfc919fbf43f6bb2aa8`

GitHub Actions run:
`34709254448`

Quality job:
- Python 3.11.16
- `ruff check .` — passed
- `ruff format --check .` — passed; 95 files already formatted
- `mypy src` — passed; no issues in 40 source files
- `pytest -q tests/unit` — 77 passed in 1.25s

Integration job:
- `docker compose config` — passed
- Qdrant `qdrant/qdrant:v1.10.1` and Redis `7.2-alpine` started successfully
- service readiness — `qdrant and redis are ready`
- `pytest -q tests/integration` — 24 passed, 1 skipped in 1.77s
- skip reason — the inherited local-OCR-only test intentionally skips on the ordinary integration
  runner because Tesseract is not installed there
- Phase 4 cleaning fixture statistics — passed
- Phase 5 chunking fixture ablation — passed
- Phase 6 dense Qdrant fixture evidence — passed
- package smoke — `rageval smoke: ok (development)`
- full `pytest -q` — 101 passed, 1 skipped in 1.70s
- `docker compose down -v` — passed

Dedicated local OCR job:
- installed Tesseract 5.3.4
- `pytest -q -m local_ocr tests/integration/test_local_ocr.py` — 1 passed in 0.46s

The Python Qdrant client resolved to `qdrant-client==1.10.1`, matching the real local Qdrant server
version used by Compose.

## Machine-readable dense fixture evidence

Command:

```bash
python scripts/dense_fixture_report.py
```

Accepted-run evidence:
- corpus fingerprint:
  `cba5fea59f8d977e403fa66dd29bc7e282d040a183946b830652ab71af262927`
- collection: `rageval_phase6_fixture__ci_v1`
- chunk strategy: `fixed_512`
- chunking config fingerprint:
  `39c2cecc397b0f815ce0aaef853187966d3af4e93b6a4bab45c843b79e7977ab`
- embedding provider: `local-hash`
- embedding model: `local-hash-embedding-v1`
- embedding dimension: 64
- evidence label: `local-hash-diagnostic-only`
- fixture documents indexed: 4
- total indexed points: 6
- domain-filter counts: financial 3, legal 2, research 1
- document chunk counts: financial report 1, legal MSA 2, financial table 2, research HTML 1
- exact-source-chunk queries returned the expected source chunk first for all four documents;
  observed cosine scores were 1.0, 1.0, 0.99999994, and 0.99999994 respectively.

Those scores are a deterministic mechanics sanity check because the query is the source chunk text
itself. They are not evidence that local hash embeddings provide production retrieval quality or that
`fixed_512` is a globally preferred chunking strategy.

## Failure and repair history

The implementation was not declared complete on first green-looking behavior:

1. Initial PR run `34708952516` reached real-Qdrant integration successfully but quality failed Ruff
   on four style defects (two long lines, one unused import, one long assertion). The style defects
   were corrected without weakening tests; integration/OCR had already passed.
2. Run `34709039970` passed lint and real-Qdrant/OCR but formatter check identified canonical layout
   changes in two files. Ruff's canonical formatting was applied exactly.
3. Run `34709149771` passed lint/format and real-Qdrant/OCR, then strict mypy exposed four Qdrant
   annotation mismatches: client timeout was typed as integer seconds, a reused batch variable
   confused the point/text sequence types, the upsert parameter required a concrete list, and
   payload `.get()` needed explicit narrowing. These were fixed at the source with an integer timeout
   contract, distinct typed batch variables, `list(point_batch)`, and explicit payload/chunk-ID
   narrowing. No `type: ignore` or reduced strictness was added.
4. Run `34709254448` reran the full cumulative suite and passed all three jobs.

No tests, assertions, lint rules, mypy strictness, real-service checks, Phase 4 cleaning evidence,
Phase 5 chunking evidence, full regression, or installed-Tesseract OCR validation were weakened.

## Provider validation and blockers

### Deterministic/local validation — passed

The local hash dense provider, provider contract behavior, Qdrant indexing, filtering, lifecycle,
consistency, and end-to-end retrieval were all exercised deterministically. Real Qdrant was used;
it was not mocked away.

### Hosted OpenAI validation — not run

No live OpenAI credential was available to the acceptance workflow, so no live
`text-embedding-3-large` request is claimed as passed. The hosted adapter is covered with an injected
`httpx.MockTransport` for request shape, returned-index ordering, vector-dimension validation, and
HTTP/provider errors. A future credential-enabled live-provider tier may add a real request, but it
must remain additive to deterministic acceptance.

## Known limitations

- The committed fixture corpus used for dense evidence is four source documents producing six
  points, not the project target of roughly 12,000 real documents. No scale/read-write throughput
  claim is made.
- No representative retrieval benchmark or held-out recall/precision evaluation exists yet in
  Phase 6. Exact-source-text relevance sanity is intentionally much weaker than retrieval-quality
  evidence.
- The local hash embedding path is deterministic and credential-free but not a learned semantic
  embedding model; production semantic quality remains unvalidated without a real local/hosted model
  benchmark.
- Source-date filters work and are tested, but not every committed source fixture carries a real
  source date. The lifecycle test therefore uses explicit deterministic dates where necessary.
- `replace_document` is delete-then-upsert and can expose a transient gap between operations; it is
  not a transactional alias swap.
- Qdrant/Redis are validated as local single-node development services, not a replicated production
  deployment.
- The recorded single-run query latencies are instrumentation evidence only, not performance SLOs.

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
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated real local OCR validation remains:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

with Tesseract installed in the dedicated CI job.

## Phase 7 handoff

Phase 7 should build BM25/BM25+ sparse retrieval over the same canonical Phase 5 chunk identities
without replacing or mutating dense-index identities. Sparse results should continue to emit the
existing `RetrievalResult` contract so Phase 8 can fuse dense and sparse rankings by chunk ID.
Domain-aware tokenization/index rebuild semantics, deterministic sparse fixtures, and cumulative
regression should be made explicit. Phase 6's local-hash fixture results must not be treated as a
semantic-quality benchmark when comparing later hybrid retrieval results.
