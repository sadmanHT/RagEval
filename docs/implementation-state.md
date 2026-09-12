# Implementation State

## Completed

### Phase 1 — Repository foundation, contracts, and quality gates

Merged to `main` and revalidated after merge. The repository has strict shared contracts,
provider protocols/fakes, safe settings/logging, deterministic IDs, typed errors, Qdrant/Redis
Compose infrastructure, canonical verification commands, and GitHub Actions quality/integration
jobs.

### Phase 2 — Corpus contracts, fixtures, data governance, and evaluation split

Merged to `main` and revalidated after merge. Phase 2 established versioned corpus/evaluation
contracts, deterministic identities/fingerprints, duplicate/leakage protection, manifest tooling,
and the mixed-format fixture corpus used by later phases. Detailed evidence is in
`docs/phases/phase-02-report.md`.

### Phase 3 — Document loading, parsing, and OCR

Merged to `main` as PR #3 at commit `c898bdd8b91170cf3b371b15620f7203d79ef208` and revalidated
post-merge in GitHub Actions run `34704484873`. Quality, service-backed integration/regression, and
the dedicated installed-Tesseract OCR job all completed successfully on the merge commit.
Detailed evidence is in `docs/phases/phase-03-report.md`.

### Phase 4 — Cleaning, normalization, deduplication, and metadata integrity

Merged to `main` as PR #4 at commit `4366bb0f5a5a7a4f7184eb24fdf744d9eddfb502` and revalidated
post-merge in GitHub Actions run `34705921835`. The merge commit passed quality,
integration/regression/statistics, and dedicated installed-Tesseract OCR. Detailed evidence is in
`docs/phases/phase-04-report.md`.

### Phase 5 — Chunking engine, table awareness, and ablation harness

Merged to `main` as PR #5 at commit `33ded41494e3573552e9b3ee4dfa1371e8b5abaa`. Post-merge
GitHub Actions run `34707378361` passed quality, integration/cleaning/chunking-ablation/smoke/full
regression, and dedicated installed-Tesseract OCR. The later documentation-only closure also
repeated all three gates. Detailed evidence is in `docs/phases/phase-05-report.md` and
`docs/phases/phase-05-postmerge.md`.

Phase 5 provides fixed 256/32, 512/64, and 1024/128 plus provider-injected semantic chunking,
table-aware whole-row handling, legal/section boundaries, deterministic chunk IDs/configuration
fingerprints, provenance, debug CLI output, and machine-readable fixture ablations. The committed
fixture corpus is too small to rank strategies, so no globally preferred chunker is claimed.

### Phase 6 — Embeddings, Qdrant indexing, and dense retrieval

Phase 6 implementation has passed cumulative acceptance on PR #6. Accepted implementation head
`dbb48da4b42a0d3a041c1bfc919fbf43f6bb2aa8` passed GitHub Actions run `34709254448` before the
final documentation consolidation. The final PR head must repeat the same gates before merge, and a
post-merge `main` run is required before closure.

Implemented scope:
- dense embedding protocol with explicit provider model/dimension metadata;
- OpenAI `text-embedding-3-large` hosted adapter with explicit dimension/order/error validation;
- deterministic local-hash dense provider for credential-free mechanics/integration evidence;
- versioned Qdrant cosine collections with vector-schema validation and configurable HNSW/search
  parameters;
- payload indexes for domain, document ID, source-date ordinal, and chunking-config fingerprint;
- deterministic UUIDv5 Qdrant point identity derived from canonical Phase 5 chunk IDs;
- reconstructable payloads containing the full canonical `Chunk` plus document/provider/index
  metadata;
- idempotent upsert, delete/reindex by document, and exact document consistency checks;
- dense top-k search with domain/date/document/chunk-config filters and canonical
  `RetrievalResult` reconstruction;
- real local-Qdrant integration covering create/upsert/query/filter/replace/delete, stale schema,
  unavailable service, idempotency, and parser -> cleaner -> chunker -> embedding -> Qdrant ->
  retrieval provenance;
- permanent machine-readable dense fixture evidence in CI while retaining all Phase 1–5 and OCR
  regressions.

Accepted implementation evidence: Ruff and formatter passed with 95 files formatted; strict mypy
passed on 40 source files; 77 unit tests passed; ordinary integration passed 24 tests with one
intentional local-OCR-only skip; full cumulative regression passed 101 tests with the same skip;
and the dedicated OCR job installed Tesseract 5.3.4 and passed the real OCR test. The real Qdrant
fixture report indexed four documents into six points, with financial/legal/research domain-filter
counts 3/2/1 and exact-source-text sanity queries recovering the expected canonical chunks.

Live OpenAI validation was not run because no credential was available to the acceptance workflow;
the adapter is deterministically covered with an injected HTTP transport. Local-hash evidence is
explicitly diagnostic, not a learned semantic retrieval benchmark. Detailed evidence and limitations
are in `docs/phases/phase-06-report.md`.

## Next phase

### Phase 7 — BM25 sparse retrieval

Phase 7 should build BM25/BM25+ sparse retrieval over the same canonical Phase 5 chunk identities,
emit the existing `RetrievalResult` contract, define domain-aware tokenization and rebuild semantics,
and add deterministic sparse relevance/filter/regression evidence. It must remain compatible with
the Phase 6 dense result identity so Phase 8 can fuse rankings by chunk ID without score-normalizing
incompatible retrievers.

## Later phases

Fusion/query expansion, reranking/multi-hop, grounded generation, evaluation, serving,
observability/deployment hardening, and final release validation remain intentionally deferred to
their respective later phases.
