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

Merged to `main` as PR #6 at commit `52b49d89cfe1f3e69b0f60aee4bd463cd3411bbe` from final validated PR head `d3fc76c1ab23c4aa3d73e4eadacc8c3608162ef9`. Merge-triggered GitHub Actions run `34710743377` passed all three jobs: quality, integration with real-Qdrant dense fixture evidence and full regression, and dedicated installed-Tesseract OCR. Post-merge closure head `d8d3bf508ef5be6b076bd37e18a135c18914fd64` also repeated the complete three-job suite.

Phase 6 provides provider-abstracted dense embeddings, versioned Qdrant cosine collections, deterministic point identity, reconstructable canonical chunk payloads, lifecycle/consistency operations, metadata filters, and dense top-k `RetrievalResult` reconstruction. The deterministic local-hash provider validates mechanics only; live OpenAI validation remains unrun without credentials. Detailed evidence is in `docs/phases/phase-06-report.md`.

### Phase 7 — BM25 sparse retrieval and domain tokenization

Merged to `main` as PR #7 at commit `ec7235fd1584b6f6d35cec040cb061969991e766` from final validated PR head `2845b6f1d5bda03d7f15a0123d1c7a827df00546`. Final PR-head GitHub Actions run `34712500651` and independent post-merge `main` run `34712603029` both passed all three jobs: quality, integration with cleaning/chunking/dense/sparse evidence and full regression, and dedicated installed-Tesseract OCR.

Implemented scope:

- common result-only `Retriever.retrieve()` protocol with a non-breaking Phase 6 dense adapter;
- deterministic in-process BM25 and BM25+ scoring over canonical Phase 5 chunks;
- conservative domain-aware tokenizer preserving `10-K`, `Q3`, ticker symbols, percentages, dotted legal clause numbers, `§` references, acronyms, `BM25+`, and hyphenated technical terms;
- configurable default top-k of 20 plus versioned scoring/tokenizer configuration;
- domain/document/source-date/chunk-config eligibility filters while keeping fixed global BM25 corpus statistics;
- deterministic order-independent sparse index/configuration fingerprints;
- persisted JSON sparse snapshots with fingerprint/statistics integrity validation;
- canonical `RetrievalResult` output with original chunk IDs/configuration/provenance intact;
- JSON diagnostics for query tokens, matched terms, matched-term frequencies, score, and rank;
- permanent machine-readable sparse fixture evidence while retaining real-Qdrant dense, cleaning, chunking, smoke, full-regression, and OCR gates.

Accepted implementation evidence: Ruff and formatter passed with 100 files formatted; strict mypy passed on 46 source files; 90 unit tests passed; ordinary integration passed 25 tests with one intentional local-OCR-only skip; full cumulative regression passed 115 tests with the same skip; and dedicated installed-Tesseract OCR passed 1 test. The sparse fixture report built six canonical chunks from four source documents, produced index fingerprint `d93b6989100b8454199f41d6f2c2fb71e9ec78407fcdcaac1e599b7c7812787b`, reproduced that identity after reversed rebuild and snapshot round-trip, and retrieved the expected rank-1 chunk for deterministic financial/legal/research exact-term queries.

These sparse scores and exact-term fixtures are mechanics/provenance evidence only, not a production retrieval benchmark or evidence that BM25/BM25+ is globally better than dense retrieval. Detailed evidence and limitations are in `docs/phases/phase-07-report.md`.

## Accepted implementation — pending merge closure

### Phase 8 — Concurrent hybrid retrieval, Reciprocal Rank Fusion, and query expansion

Phase 8 implementation is accepted on draft PR #8 at head `4b6673e0aa4f63080d99730e8f4a87c9144cdc76`. GitHub Actions run `34717256908` passed quality, real-Qdrant/BM25 integration, cleaning/chunking/dense/sparse/hybrid fixture evidence, package smoke, full cumulative regression, and dedicated installed-Tesseract OCR. PR merge and independent post-merge `main` validation remain required before final closure.

Implemented scope:

- one hybrid retriever composing the existing Phase 6 dense and Phase 7 sparse search contracts rather than duplicating their scoring/index logic;
- concurrent dense and sparse branch execution with sibling cancellation and typed failure propagation;
- deterministic one-based Reciprocal Rank Fusion using `1 / (k + rank)` with default `k=60` and reference branch top-k 20;
- canonical chunk-ID deduplication, collision protection, stable tie ordering, and preservation of dense/sparse ranks, raw scores, RRF contributions, and final rank;
- common domain/document/source-date/chunk-config filters translated consistently to both branches;
- optional versioned/fingerprinted query expansion behind an async provider boundary;
- deterministic dictionary expansion baseline with bounded count/length, deduplication, and guaranteed original-query retention;
- per-branch and total latency diagnostics plus a sequential diagnostic path for measured local comparison;
- permanent hybrid fixture evidence while retaining every previous cleaning/chunking/dense/sparse/full-regression/OCR gate.

Accepted implementation evidence: Ruff passed and formatter reported 110 files already formatted; strict mypy passed on 51 source files; 103 unit tests passed; ordinary integration passed 26 tests with one intentional local-OCR-only skip; full cumulative regression passed 129 tests with the same skip; and dedicated Tesseract 5.3.4 validation passed 1 test. The hybrid report built 6 canonical chunks from 4 source documents with hybrid config fingerprint `37c45f72ab83fb04e27f4185e7f56456b5b6ea462adca6598093b7195a680c08`, recovered the expected lexical chunk with dense rank 1 + sparse rank 1, and demonstrated observable bounded `turnover -> revenue` expansion.

The three-sample local timing fixture did not show a concurrency speedup: concurrent median was approximately 6.382 ms and sequential median approximately 6.221 ms. This is recorded as negative timing evidence, not converted into an improvement claim. The local-hash dense provider remains mechanics-only evidence, and no hosted expansion provider or target-corpus hybrid benchmark is claimed. Detailed evidence and limitations are in `docs/phases/phase-08-report.md`.

## Next phase

### Phase 9 — Reranking and multi-hop retrieval service

Phase 9 should consume Phase 8 fused candidates by canonical `chunk_id`, add cross-encoder/hosted reranking behind explicit provider abstractions, and preserve dense/sparse/RRF/query-expansion diagnostics through the reranked result set. Multi-hop behavior must remain diagnosable and evaluation-backed rather than silently broadening retrieval.

## Later phases

Grounded generation, evaluation, serving, observability/deployment hardening, and final release validation remain intentionally deferred to their respective later phases.
