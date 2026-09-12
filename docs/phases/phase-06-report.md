# Phase 6 Report — Embeddings, Qdrant Indexing & Dense Retrieval

## Status

Phase 6 is completed, merged, and post-merge verified on `main`.

- PR: #6 — `Phase 6: embeddings, Qdrant indexing, and dense retrieval`
- final validated PR head: `d3fc76c1ab23c4aa3d73e4eadacc8c3608162ef9`
- merge commit: `52b49d89cfe1f3e69b0f60aee4bd463cd3411bbe`
- merge-triggered `main` CI run: `34710743377`
- result: quality, integration/regression/dense evidence, and installed-Tesseract OCR all succeeded

The accepted implementation head before final documentation consolidation was `dbb48da4b42a0d3a041c1bfc919fbf43f6bb2aa8`, which passed run `34709254448`. The final PR head repeated the same gates before merge, and the merge commit repeated them again on `main`.

## Mission delivered

Phase 6 adds a reproducible dense-retrieval boundary over canonical Phase 5 chunks. The system can embed chunks behind a provider abstraction, create and validate a versioned Qdrant collection, idempotently index reconstructable chunk payloads, filter and search them, replace/delete document contents, detect index inconsistencies, and reconstruct the existing canonical `RetrievalResult` contract from real local Qdrant results.

No sparse retrieval, fusion, reranking, generation, or evaluation-runner functionality is included; those remain later-phase scope.

## Architecture decisions

### Embedding providers

- The existing embedding boundary remains source-compatible for Phase 5 semantic chunking.
- Phase 6 adds a dense embedding protocol with explicit `model` and `dimension` metadata needed for vector-schema validation.
- `OpenAIEmbeddingProvider` targets `text-embedding-3-large` with a 3072-dimensional default, supports explicit requested dimensions, validates returned index ordering and vector length, and converts HTTP/provider failures to project `ProviderError` values.
- `LocalHashDenseEmbeddingProvider` is deterministic, credential-free mechanics evidence only. It is not treated as a learned semantic-quality benchmark.
- No hosted embedding fine-tuning capability is claimed.

### Qdrant schema and identity

- Collections use versioned names: `<collection_base>__<collection_version>`.
- One unnamed cosine vector is used with explicit dimensional validation.
- HNSW construction and search parameters are configuration-owned.
- Existing collection vector size and distance are validated before use; stale schemas fail explicitly and require a collection-version bump or rebuild.
- Payload indexes cover `domain`, `document_id`, `source_date_ordinal`, and `chunking_config_fingerprint`.
- Qdrant point IDs are deterministic UUIDv5 values derived from canonical project `chunk_id` values, preserving stable reingestion identity while retaining the original chunk ID in payloads.

### Payloads and lifecycle

Each point stores the full canonical serialized `Chunk` plus document/source metadata, chunking fingerprint, embedding provider/model/dimension, collection version, and source date when available.

Supported lifecycle behavior includes:
- idempotent document upsert;
- delete by document;
- delete-then-upsert document replacement;
- exact expected-versus-indexed chunk consistency checks.

`replace_document` is intentionally not described as transactional; it can expose a transient gap between delete and upsert.

### Dense search

Search supports top-k plus domain, source-date range, document ID, and chunking-config filters. Query embedding latency, Qdrant latency, and total latency are measured independently. Results reconstruct the canonical `Chunk` and existing `RetrievalResult` contract. Equal-score ordering is stabilized with `chunk_id` as the secondary key.

Recorded fixture latencies are instrumentation evidence only, not production SLO or load-test evidence.

## Verification evidence

### Accepted implementation run — `34709254448`

Quality:
- Python 3.11.16
- `ruff check .` — passed
- `ruff format --check .` — passed; 95 files formatted
- `mypy src` — passed; no issues in 40 source files
- `pytest -q tests/unit` — 77 passed

Integration:
- Compose validation passed
- Qdrant `v1.10.1` and Redis `7.2-alpine` started successfully
- service readiness passed
- `pytest -q tests/integration` — 24 passed, 1 intentional local-OCR-only skip
- Phase 4 cleaning evidence passed
- Phase 5 chunking ablation passed
- Phase 6 dense Qdrant fixture evidence passed
- package smoke passed
- full `pytest -q` — 101 passed, 1 same intentional skip
- clean Compose teardown passed

Dedicated OCR:
- installed Tesseract 5.3.4
- real OCR fixture — 1 passed

### Final PR-head validation

Final PR head `d3fc76c1ab23c4aa3d73e4eadacc8c3608162ef9` repeated quality, integration/regression/dense evidence, and installed-Tesseract OCR successfully before PR #6 was marked ready and merged.

### Post-merge `main` validation — `34710743377`

Merge commit `52b49d89cfe1f3e69b0f60aee4bd463cd3411bbe` independently passed all three jobs on `main`:
- `quality` — success
- `integration` — success, including cleaning statistics, chunking ablation, dense Qdrant fixture evidence, package smoke, full regression, and clean teardown
- `local-ocr` — success with installed Tesseract

No acceptance gate was weakened during Phase 6.

## Machine-readable dense fixture evidence

Canonical command:

```bash
python scripts/dense_fixture_report.py
```

Accepted evidence:
- corpus fingerprint: `cba5fea59f8d977e403fa66dd29bc7e282d040a183946b830652ab71af262927`
- collection: `rageval_phase6_fixture__ci_v1`
- chunk strategy: `fixed_512`
- chunking config fingerprint: `39c2cecc397b0f815ce0aaef853187966d3af4e93b6a4bab45c843b79e7977ab`
- embedding provider: `local-hash`
- embedding model: `local-hash-embedding-v1`
- embedding dimension: 64
- evidence label: `local-hash-diagnostic-only`
- source documents indexed: 4
- indexed points: 6
- domain-filter counts: financial 3, legal 2, research 1
- exact-source-text sanity queries returned the expected source chunk first for all four documents

These are deterministic mechanics checks. They do not establish production semantic quality or prove `fixed_512` is an optimal chunking strategy.

## Failure and repair history

Phase 6 was not declared complete on the first working implementation:

1. Initial PR CI reached real Qdrant successfully but Ruff found four style defects. They were fixed without changing test coverage.
2. The next run exposed two canonical formatter differences; Ruff formatting was applied exactly.
3. Strict mypy then exposed four Qdrant-client typing issues: integer timeout typing, a reused batch variable, concrete-list upsert typing, and payload narrowing. These were fixed at the source without `type: ignore` or weakened strictness.
4. Run `34709254448` passed the complete cumulative suite.
5. The final documentation head repeated the suite before merge.
6. Merge-triggered run `34710743377` passed independently on `main`.

## Provider validation

### Deterministic/local — passed

The local dense provider, provider contracts, Qdrant indexing, filtering, lifecycle, consistency, failure handling, and end-to-end retrieval were exercised deterministically against a real local Qdrant service.

### Hosted OpenAI — not run

No live OpenAI credential was available to CI, so no real `text-embedding-3-large` request is claimed as passed. The hosted adapter is covered with an injected `httpx.MockTransport` for request shape, returned-index ordering, vector-dimension validation, and HTTP/provider error behavior.

A future credential-enabled live-provider tier may add a real request, but it must remain additive to deterministic acceptance.

## Known limitations and non-claims

- The fixture evidence is four source documents and six points, not the target ~12k-document corpus.
- No held-out retrieval recall/precision benchmark exists yet for dense retrieval.
- The local hash provider is not a learned semantic model.
- Source-date filters are tested, but not every committed fixture has a real source date.
- Document replacement is delete-then-upsert rather than transactional alias switching.
- Qdrant/Redis validation is single-node local development infrastructure, not production HA validation.
- Query latencies are instrumentation checks only.
- No live OpenAI success, production throughput, production-ready claim, or optimal chunking/embedding strategy is asserted.

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

Dedicated real OCR validation remains:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

with Tesseract installed in the dedicated CI job.

## Phase 7 handoff

Phase 7 should build BM25/BM25+ sparse retrieval over the same canonical Phase 5 chunk identities without mutating dense-index identities. Sparse retrieval should emit the existing `RetrievalResult` contract so Phase 8 can fuse dense and sparse rankings by chunk ID. Domain-aware tokenization, deterministic index/rebuild semantics, sparse relevance fixtures, filters, and cumulative regression evidence should be explicit. Phase 6 local-hash fixture results must not be treated as a semantic-quality benchmark when later hybrid retrieval is evaluated.
