# Implementation State

## Completed

### Phase 1 — Repository foundation, contracts, and quality gates

Merged to `main` and revalidated after merge. The repository has strict shared contracts, provider protocols/fakes, safe settings/logging, deterministic IDs, typed errors, Qdrant/Redis Compose infrastructure, canonical verification commands, and GitHub Actions quality/integration jobs.

### Phase 2 — Corpus contracts, fixtures, data governance, and evaluation split

Merged to `main` and revalidated after merge. Phase 2 established versioned corpus/evaluation contracts, deterministic identities/fingerprints, duplicate/leakage protection, manifest tooling, and the mixed-format fixture corpus used by later phases. Detailed evidence is in `docs/phases/phase-02-report.md`.

### Phase 3 — Document loading, parsing, and OCR

Merged to `main` as PR #3 at commit `c898bdd8b91170cf3b371b15620f7203d79ef208` and revalidated post-merge in GitHub Actions run `34704484873`. Quality, service-backed integration/regression, and dedicated installed-Tesseract OCR all passed. Detailed evidence is in `docs/phases/phase-03-report.md`.

### Phase 4 — Cleaning, normalization, deduplication, and metadata integrity

Merged to `main` as PR #4 at commit `4366bb0f5a5a7a4f7184eb24fdf744d9eddfb502` and revalidated post-merge in GitHub Actions run `34705921835`. Quality, integration/regression/statistics, and dedicated installed-Tesseract OCR passed. Detailed evidence is in `docs/phases/phase-04-report.md`.

### Phase 5 — Chunking engine, table awareness, and ablation harness

Merged to `main` as PR #5 at commit `33ded41494e3573552e9b3ee4dfa1371e8b5abaa`. Post-merge GitHub Actions run `34707378361` passed quality, integration/cleaning/chunking-ablation/smoke/full regression, and dedicated installed-Tesseract OCR. Later documentation-only closure commits also repeated all three gates. Detailed evidence is in `docs/phases/phase-05-report.md` and `docs/phases/phase-05-postmerge.md`.

Phase 5 provides fixed 256/32, 512/64, and 1024/128 plus provider-injected semantic chunking, table-aware whole-row handling, legal/section boundaries, deterministic chunk IDs/configuration fingerprints, provenance, debug CLI output, and machine-readable fixture ablations. The committed fixture corpus is too small to rank strategies, so no globally preferred chunker is claimed.

### Phase 6 — Embeddings, Qdrant indexing, and dense retrieval

Merged to `main` as PR #6 at commit `52b49d89cfe1f3e69b0f60aee4bd463cd3411bbe` from final validated PR head `d3fc76c1ab23c4aa3d73e4eadacc8c3608162ef9`. Merge-triggered GitHub Actions run `34710743377` passed all three jobs: quality, integration with real-Qdrant dense fixture evidence and full regression, and dedicated installed-Tesseract OCR.

Implemented scope:
- dense embedding provider boundary with explicit provider/model/dimension metadata;
- hosted OpenAI `text-embedding-3-large` adapter with explicit request/ordering/dimension/error validation;
- deterministic local-hash dense provider for credential-free mechanics and integration evidence;
- versioned Qdrant cosine collections with vector-schema validation and configurable HNSW/search parameters;
- payload indexes for domain, document ID, source-date ordinal, and chunking-config fingerprint;
- deterministic UUIDv5 Qdrant point IDs derived from canonical Phase 5 chunk IDs;
- reconstructable payloads containing the full canonical `Chunk` plus document/provider/index metadata;
- idempotent upsert, delete/reindex by document, and exact document consistency checks;
- dense top-k search with domain/date/document/chunk-config filters and canonical `RetrievalResult` reconstruction;
- real local-Qdrant integration for collection lifecycle, filters, stale-schema handling, service failure handling, idempotency, and parser -> cleaner -> chunker -> embedding -> Qdrant -> retrieval provenance;
- permanent machine-readable dense fixture evidence while retaining all prior cleaning/chunking/OCR regressions.

Verified evidence on the accepted implementation and merge commit includes Ruff and formatter success, strict mypy on 40 source files, 77 unit tests, 24 ordinary integration tests with one intentional local-OCR-only skip, 101 cumulative regression tests with the same skip, Qdrant/Redis startup and clean teardown, and one real installed-Tesseract OCR test. The dense fixture report indexed four source documents into six Qdrant points with financial/legal/research filter counts 3/2/1 and exact-source-text sanity queries recovering the expected canonical chunks.

Live OpenAI validation was not run because no hosted credential was available to CI. The hosted adapter is deterministically tested with an injected HTTP transport. Local-hash evidence is diagnostic mechanics evidence only, not a learned semantic retrieval benchmark. Detailed evidence and limitations are in `docs/phases/phase-06-report.md`.

## Next phase

### Phase 7 — BM25 sparse retrieval

Phase 7 should build BM25/BM25+ sparse retrieval over the same canonical Phase 5 chunk identities, emit the existing `RetrievalResult` contract, define domain-aware tokenization and deterministic index/rebuild semantics, and add sparse relevance/filter/regression evidence. Sparse result identity must remain compatible with Phase 6 dense results so Phase 8 can fuse rankings by chunk ID without score-normalizing incompatible retrievers.

## Later phases

Fusion/query expansion, reranking/multi-hop, grounded generation, evaluation, serving, observability/deployment hardening, and final release validation remain intentionally deferred to their respective later phases.
