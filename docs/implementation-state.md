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

Merged to `main` as PR #5 at commit `33ded41494e3573552e9b3ee4dfa1371e8b5abaa`. Post-merge run `34707378361` passed quality, integration/cleaning/chunking-ablation/smoke/full regression, and dedicated installed-Tesseract OCR. Detailed evidence is in `docs/phases/phase-05-report.md` and `docs/phases/phase-05-postmerge.md`.

Phase 5 provides fixed 256/32, 512/64, and 1024/128 plus provider-injected semantic chunking, table-aware whole-row handling, legal/section boundaries, deterministic chunk IDs/configuration fingerprints, provenance, debug CLI output, and machine-readable fixture ablations. The committed fixture corpus is too small to rank strategies, so no globally preferred chunker is claimed.

### Phase 6 — Embeddings, Qdrant indexing, and dense retrieval

Merged to `main` as PR #6 at commit `52b49d89cfe1f3e69b0f60aee4bd463cd3411bbe` from final validated PR head `d3fc76c1ab23c4aa3d73e4eadacc8c3608162ef9`. Merge-triggered run `34710743377` passed all three jobs, and post-merge closure head `d8d3bf508ef5be6b076bd37e18a135c18914fd64` repeated the complete suite.

Phase 6 provides provider-abstracted dense embeddings, versioned Qdrant cosine collections, deterministic point identity, reconstructable canonical chunk payloads, lifecycle/consistency operations, metadata filters, and dense top-k `RetrievalResult` reconstruction. The deterministic local-hash provider validates mechanics only; live OpenAI validation remains unrun without credentials. Detailed evidence is in `docs/phases/phase-06-report.md`.

### Phase 7 — BM25 sparse retrieval and domain tokenization

Merged to `main` as PR #7 at commit `ec7235fd1584b6f6d35cec040cb061969991e766` from final validated PR head `2845b6f1d5bda03d7f15a0123d1c7a827df00546`. Final PR-head run `34712500651` and independent post-merge run `34712603029` both passed all three jobs.

Phase 7 provides deterministic in-process BM25/BM25+ over canonical chunks, domain-aware lexical tokenization, default top-k 20, stable filters, deterministic sparse snapshots/fingerprints, canonical `RetrievalResult` output, and lexical diagnostics. Accepted implementation evidence was 90 unit tests, 25 integration tests plus one intentional local-OCR skip, 115 cumulative tests plus the same skip, and one dedicated installed-Tesseract OCR test. Detailed evidence is in `docs/phases/phase-07-report.md`.

### Phase 8 — Concurrent hybrid retrieval, Reciprocal Rank Fusion, and query expansion

Merged to `main` as PR #8 at commit `b5d9b2d6d2b1f079ebe16f9a3119d35f83aa6cde` from final validated PR head `e012de44d07e26059d7ccab7d040da2313be07dc`. Final PR-head run `34717434998`, independent post-merge run `34717496000`, and closure-head run `34717599356` passed all three jobs.

Phase 8 composes dense and sparse retrieval concurrently, fuses canonical identities with deterministic one-based RRF using `1 / (k + rank)` and default `k=60`, preserves branch ranks/raw scores/contributions, applies equivalent filters, supports bounded observable query expansion, and records latency diagnostics. Accepted implementation evidence was 103 unit tests, 26 integration tests plus one intentional local-OCR skip, 129 cumulative tests plus the same skip, strict mypy on 51 source files, and one dedicated Tesseract test. The tiny local timing fixture did not demonstrate a concurrency speedup, and this negative evidence is retained. Detailed evidence is in `docs/phases/phase-08-report.md`.

### Phase 9 — Neural reranking, retrieval service, and multi-hop retrieval

Merged to `main` as PR #9 at commit `0cf47f8dc7a2b3ae44c331cb287242c81284ce14` from final validated PR head `28fa30cb6ee3997b02023c6cf2f54c07b8348f69`. Final PR-head GitHub Actions run `34718753817` and independent post-merge `main` run `34718825100` both passed all three jobs: quality, integration with cleaning/chunking/dense/sparse/hybrid/reranked-service evidence plus full regression, and dedicated installed-Tesseract OCR.

Implemented scope:

- async `RerankerProvider` abstraction;
- deterministic fake reranker for credential-free acceptance mechanics;
- Cohere Rerank hosted reference adapter with bounded timeout, retry attempts, exponential backoff, retryable 429/5xx behavior, and strict response validation;
- reranking over existing canonical Phase 8 `RetrievalResult` objects rather than reconstructed chunks;
- default final top-5 context with pre-rerank rank, post-rerank rank, rerank score, provider/model identity, and deterministic rerank configuration fingerprint;
- retrieval-service orchestration from normalized query through Phase 8 hybrid retrieval, optional multi-hop, canonical-ID merge, reranking, and final context;
- multi-hop modes `off`, `always`, and `rule`, with `off` as the default so ordinary queries do not pay second-hop cost;
- conservative reference-aware rule planner plus injectable planner protocol;
- bounded second-hop queries and merged candidate budgets;
- per-hop query/retrieval-query/expansion/candidate/fingerprint/latency diagnostics;
- permanent real-Qdrant/BM25/RRF/rerank/multi-hop fixture evidence while retaining every previous CI gate.

Accepted implementation evidence: Ruff passed; formatter reported **123 files already formatted**; strict mypy passed on **59 source files**; unit suite **114 passed**; ordinary integration **27 passed, 1 skipped**; full cumulative suite **141 passed, 1 skipped**; dedicated installed Tesseract 5.3.4 OCR **1 passed**.

The Phase 9 fixture builds **6 canonical chunks from 4 committed source documents**. Its sparse index fingerprint is `cb40c6bc98ba218751b4b926bce19148466b97f932a2fdfbc671ff1f4a8f8c43`, service fingerprint is `1fb23ec813c4ef27b156ac654620effed71f0c6154f995f50128c8bccdfd6856`, and rerank fingerprint is `e1db77ff3b191e124eb9583de7eec473d0e6bf3e88d004fe1514d22ff09032f2`. The deterministic rerank fixture moved canonical chunk `chk_51e3471b7f313a1a164a57e03397043f` from pre-rerank rank 6 to post-rerank rank 1 while retaining the original retrieval/provenance object. The two-hop legal fixture recovered `chk_1546d99922b41acf731a9877e524839e` after first-hop top-1 omitted it and retained both hop traces.

These are mechanics/provenance results, not neural-reranking or target-corpus quality results. Live Cohere validation was not run without credentials, and no local neural cross-encoder adapter is implemented, so full offline *neural* reranking is not currently available. Detailed evidence and limitations are in `docs/phases/phase-09-report.md`.

### Phase 10 — Grounded generation, context assembly, citations, and Self-RAG routing

Merged to `main` as PR #10 at commit `87c2c329a12aa4fc3d4a5eb775ed2df32c3ce111` from final validated PR head `ec550e6cb1251f9dbb65894c3adc470fa2dd7456`. Final PR-head GitHub Actions run `34806206207` and independent merge-triggered `main` run `34806319174` both passed all three jobs: quality, integration with every inherited evidence gate plus the grounded-generation fixture and full regression, and dedicated installed-Tesseract OCR.

Implemented scope:

- deterministic context assembly over the canonical Phase 9 final reranked context;
- stable rank ordering, explicit chunk/source metadata, separators, context-budget enforcement, deterministic truncation, and duplicate/near-duplicate suppression;
- context and generation configuration fingerprints for later evaluation/audit;
- provider-abstracted generation with deterministic fake acceptance and an OpenAI hosted reference adapter;
- bounded OpenAI timeout/retry/backoff behavior with retryable 429/5xx/network/timeout handling and strict response/usage parsing;
- structured grounded-answer parsing, canonical cited-chunk IDs, token/latency/provider/model/refusal metadata, and backward-compatible defaulted contract extensions;
- application-side validation that cited chunk IDs exist in the exact supplied context;
- bounded repair for malformed structured output, invalid citations, and inconsistent refusal state, with repair records and fail-closed exhaustion;
- explicit insufficient-context refusal with zero citations;
- prompt boundary that treats retrieved document instructions as untrusted data rather than system instructions;
- default `AlwaysRetrieveRouter` plus opt-in conservative Self-RAG-style routing whose no-retrieval path refuses rather than producing an ungrounded answer under the grounded guarantee;
- end-to-end service preserving the Phase 9 retrieval response and retrieval/rerank/multi-hop fingerprints in answer diagnostics;
- permanent real-Qdrant/BM25/RRF/rerank/generation fixture evidence while retaining every previous CI gate.

Accepted implementation evidence: Ruff passed; formatter reported **135 files already formatted**; strict mypy passed on **66 source files**; unit suite **125 passed**; ordinary integration **28 passed, 1 skipped**; full cumulative suite **153 passed, 1 skipped**; dedicated installed Tesseract 5.3.4 OCR **1 passed**.

The Phase 10 fixture builds **6 canonical chunks from 4 committed source documents**. The answerable path cites `chk_0aa1f9408acc9a91748da01bf8ba93ee`, which is present in the exact supplied assembled context. The intentionally unsupported question `What is the lunar population of Europa in 2125?` returns `insufficient_context=true` with zero citations. Generation configuration fingerprint is `6b2bba681505a024536b962965e3e754190fde07416b7689ae8f976be607b508`; context configuration fingerprint is `3e21ad11a5cf2934c6babde30cce2247bec8a4f8d8c42fc8e5f50cf2467c0f42`.

These are mechanics/traceability results, not hosted-model quality or semantic-faithfulness results. Live OpenAI generation was not run without credentials. Citation validation currently proves canonical ID membership in supplied context, not claim entailment. Context token accounting is deterministic mechanics accounting rather than exact hosted-model tokenization. Detailed evidence and limitations are in `docs/phases/phase-10-report.md`.

### Phase 11 — Evaluation dataset, metric implementations, and judge contracts

Merged to `main` as PR #11 at commit `5cdfcaa409545cc448a8a3d99ecfd066c0239a8a` from final validated PR head `e3e2bd1388961fe8c5ba83c57a7be6f8066f60a8`. Final PR-head GitHub Actions run `34819678161` and independent merge-triggered `main` run `34819832613` both passed all three jobs: quality, integration with every inherited evidence gate plus the Phase 11 evaluation-metrics fixture and full regression, and dedicated installed-Tesseract OCR.

Phase 11 provides leakage-aware evaluation dataset contracts and JSONL/review tooling; deterministic dataset/config/run fingerprints; canonical chunk-ID context precision/recall; structured provider-abstracted judge requests/responses with concise rationale/evidence fields and explicit prompt/rubric/provider/model versions; deterministic rule/scripted judges; claim-level faithfulness and answer relevancy; response-level hallucination defined strictly as `faithfulness < 0.8`; count/denominator-validated hallucination aggregation; and an optional stable RAGAS adapter boundary around an injected scorer.

Accepted implementation evidence: Ruff passed; formatter reported **149 files already formatted**; strict mypy passed on **71 source files**; unit suite **147 passed**; ordinary integration **29 passed, 1 skipped**; full cumulative suite **176 passed, 1 skipped**; dedicated installed Tesseract 5.3.4 OCR **1 passed**.

The Phase 11 acceptance fixture contains **3 reviewed synthetic examples**, not the target roughly 200-question held-out set. Its dataset fingerprint is `5dad39bffb7acd7ac15414a10b9a654461a4ba0ff4642f7c66281733fd9c4cc0`, configuration fingerprint is `89fbf59dba96baec81e6437d22b50451fcb697327adc4249f854173dbf698d38`, and run fingerprint is `487bfc426c609b97c65f660626d75b9672281b89deee94be361a98017c69e858`. The deterministic fixture produced one flagged response out of three at the strict `< 0.8` threshold, so the persisted hallucination rate is computed as `1 / 3`, not copied from documentation.

These are mechanics/arithmetic results, not representative semantic-quality results. No target 200-question dataset was supplied or fabricated, no live LLM judge was run, and no actual RAGAS package-backed evaluation result is claimed. Detailed evidence and limitations are in `docs/phases/phase-11-report.md`.

## Next phase

### Phase 12 — Evaluation runner, ablation, and failure analysis

Phase 12 should consume the stable Phase 11 dataset/metric/judge/run contracts to run reproducible configuration-specific evaluations, persist traceable artifacts, execute controlled retrieval/generation ablations, slice results by domain/tags/table cases, and produce failure analysis without mixing dataset or metric versions. Representative benchmark claims remain blocked until the real reviewed evaluation set and any required provider credentials are supplied.

## Later phases

Serving, observability/deployment hardening, and final release validation remain intentionally deferred to their respective later phases.
