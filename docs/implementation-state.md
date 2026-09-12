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

Merged to `main` as PR #6 at commit `52b49d89cfe1f3e69b0f60aee4bd463cd3411bbe` from final validated PR head `d3fc76c1ab23c4aa3d73e4eadacc8c3608162ef9`. Merge-triggered GitHub Actions run `34710743377` passed all three jobs. Post-merge closure head `d8d3bf508ef5be6b076bd37e18a135c18914fd64` repeated the complete three-job suite.

Phase 6 provides provider-abstracted dense embeddings, versioned Qdrant cosine collections, deterministic point identity, reconstructable canonical chunk payloads, lifecycle/consistency operations, metadata filters, and dense top-k `RetrievalResult` reconstruction. The deterministic local-hash provider validates mechanics only; live OpenAI validation remains unrun without credentials. Detailed evidence is in `docs/phases/phase-06-report.md`.

### Phase 7 — BM25 sparse retrieval and domain tokenization

Merged to `main` as PR #7 at commit `ec7235fd1584b6f6d35cec040cb061969991e766` from final validated PR head `2845b6f1d5bda03d7f15a0123d1c7a827df00546`. Final PR-head run `34712500651` and independent post-merge run `34712603029` both passed all three jobs.

Phase 7 provides deterministic in-process BM25/BM25+ over canonical Phase 5 chunks, domain-aware lexical tokenization, default top-k 20, stable filters, deterministic sparse snapshots/fingerprints, canonical `RetrievalResult` output, and query-token/matched-term/rank/score diagnostics. Accepted implementation evidence was 90 unit tests, 25 integration tests plus one intentional local-OCR skip, 115 cumulative tests plus the same skip, and one dedicated installed-Tesseract OCR test. Detailed evidence is in `docs/phases/phase-07-report.md`.

### Phase 8 — Concurrent hybrid retrieval, Reciprocal Rank Fusion, and query expansion

Merged to `main` as PR #8 at commit `b5d9b2d6d2b1f079ebe16f9a3119d35f83aa6cde` from final validated PR head `e012de44d07e26059d7ccab7d040da2313be07dc`. Final PR-head run `34717434998` and independent post-merge run `34717496000` both passed all three jobs; final closure head `1da7c2bea16689bf8e0d1650d3b7f0b82fb0872e` also passed run `34717599356`.

Phase 8 composes the existing dense and sparse paths concurrently, fuses canonical identities with deterministic one-based Reciprocal Rank Fusion using `1 / (k + rank)` and default `k=60`, preserves branch ranks/raw scores/contributions, applies equivalent filters, supports bounded observable query expansion, and records latency diagnostics. Accepted implementation evidence was 103 unit tests, 26 integration tests plus one intentional local-OCR skip, 129 cumulative tests plus the same skip, strict mypy on 51 source files, and one dedicated Tesseract test. The tiny local timing fixture did not demonstrate a concurrency speedup, and this negative evidence is retained. Detailed evidence is in `docs/phases/phase-08-report.md`.

## Accepted implementation — pending merge closure

### Phase 9 — Neural reranking, retrieval service, and multi-hop retrieval

Phase 9 implementation is accepted on draft PR #9 at head `48ac34e791893dca3c119925648738cc97599a7a`. GitHub Actions run `34718531754` passed quality, real-Qdrant/BM25 integration, every inherited cleaning/chunking/dense/sparse/hybrid fixture gate, the new reranked retrieval-service evidence, package smoke, full cumulative regression, and dedicated installed-Tesseract OCR. PR merge and independent post-merge `main` validation remain required before final closure.

Implemented scope:

- async `RerankerProvider` abstraction;
- deterministic fake reranker for credential-free acceptance;
- Cohere Rerank hosted reference adapter with bounded timeout, retry attempts, exponential backoff, retryable 429/5xx behavior, and strict response validation;
- reranking over the existing canonical Phase 8 `RetrievalResult` objects rather than reconstructed chunks;
- default final top-5 context with pre-rerank rank, post-rerank rank, rerank score, provider/model identity, and deterministic rerank configuration fingerprint;
- retrieval-service orchestration from normalized query through Phase 8 hybrid retrieval, optional multi-hop, canonical-ID merge, reranking, and final context;
- multi-hop modes `off`, `always`, and `rule`, with `off` as the default so ordinary queries do not pay second-hop cost;
- conservative reference-aware rule planner plus an injectable planner protocol;
- bounded second-hop queries and merged candidate budgets;
- per-hop diagnostics including query, effective retrieval query, expansion state, candidate IDs, hybrid fingerprint, and branch/total latency;
- permanent real-Qdrant/BM25/RRF/rerank/multi-hop fixture evidence while retaining every previous CI gate.

Accepted implementation evidence:

- Ruff passed;
- Ruff formatter reported **123 files already formatted**;
- strict mypy passed on **59 source files**;
- unit suite: **114 passed**;
- ordinary integration: **27 passed, 1 skipped** (the inherited local-OCR-only test because Tesseract is intentionally absent from that runner);
- full cumulative suite: **141 passed, 1 skipped**;
- dedicated installed Tesseract 5.3.4 OCR: **1 passed**.

The Phase 9 fixture builds **6 canonical chunks from 4 committed source documents**. Its sparse index fingerprint is `cb40c6bc98ba218751b4b926bce19148466b97f932a2fdfbc671ff1f4a8f8c43`, service fingerprint is `1fb23ec813c4ef27b156ac654620effed71f0c6154f995f50128c8bccdfd6856`, and rerank fingerprint is `e1db77ff3b191e124eb9583de7eec473d0e6bf3e88d004fe1514d22ff09032f2`. The deterministic rerank fixture moved canonical chunk `chk_51e3471b7f313a1a164a57e03397043f` from pre-rerank rank 6 to post-rerank rank 1 while retaining its original retrieval/provenance object. The two-hop legal fixture recovered `chk_1546d99922b41acf731a9877e524839e` after first-hop top-1 omitted it and retained both hop traces.

These are mechanics/provenance results, not neural-reranking or target-corpus quality results. Live Cohere validation is unrun without credentials, and no local neural cross-encoder adapter is implemented, so full offline *neural* reranking is not currently available. Detailed evidence, failure/repair history, and limitations are in `docs/phases/phase-09-report.md`.

## Next phase

### Phase 10 — Grounded generation, citations, and self-RAG

Phase 10 should consume the final ordered Phase 9 `RerankResult` context set while preserving all nested dense/sparse/RRF/query-expansion/rerank/hop diagnostics and canonical source provenance. Generation should assemble structured context, cite canonical chunk IDs for claims, refuse when evidence is insufficient, keep LLM providers behind explicit interfaces, and make any self-RAG/verification behavior observable and evaluation-ready.

## Later phases

Evaluation, serving, observability/deployment hardening, and final release validation remain intentionally deferred to their respective later phases.
