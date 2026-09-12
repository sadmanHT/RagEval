# Phase 9 Plan — Neural Reranking, Retrieval Service & Multi-hop Retrieval

## Status

Implementation accepted on PR #9 at head `48ac34e791893dca3c119925648738cc97599a7a` by GitHub Actions run `34718531754`. Merge and independent post-merge `main` validation are still required before Phase 9 closure.

## Mission

Turn Phase 8 fused hybrid candidates into a high-precision retrieval-service output by adding a provider-abstracted reranking stage, a default final context size of five, and bounded multi-hop retrieval for queries that genuinely require non-adjacent evidence.

## Preserved contracts

Phase 9 composes, rather than replaces, the existing retrieval stack:

1. parse/clean/chunk contracts remain unchanged;
2. Phase 6 dense Qdrant and Phase 7 BM25/BM25+ continue to own their scoring/index behavior;
3. Phase 8 `HybridRetriever.search()` remains the source of fused `RetrievalResult` candidates and expansion/filter diagnostics;
4. reranking wraps the canonical `RetrievalResult` in the existing `RerankResult` contract so chunk identity and provenance are not reconstructed or discarded.

## Implementation plan

### Reranking

- `RerankerProvider` is the provider boundary.
- `DeterministicFakeReranker` is the credential-free acceptance baseline and validates mechanics only.
- `CohereReranker` is the hosted reference adapter, using Cohere Rerank v2 HTTP semantics with configurable model identity, bounded request timeout, bounded attempts, exponential backoff, and retryable 429/5xx handling.
- `RerankingEngine` validates returned candidate indexes, rejects duplicates/out-of-range indexes, deterministically orders ties, fingerprints provider/model/configuration identity, and emits final `RerankResult` objects.
- Default final context size is five.

### Retrieval service

`RetrievalService` performs:

1. whitespace normalization;
2. Phase 8 hybrid retrieval (default candidate budget 20);
3. optional multi-hop decision and bounded second-hop retrieval;
4. canonical chunk-ID merge with collision protection;
5. reranking on the original normalized user query;
6. final top-N context plus service/rerank/hop diagnostics.

### Multi-hop

Multi-hop is not paid by default. `MultiHopMode.OFF` is the default. `ALWAYS` supports explicit opt-in, and `RULE` uses an injectable planner. The deterministic local `ReferenceAwareMultiHopPlanner` conservatively requires a relation cue plus an explicit section/clause/appendix/schedule reference found in first-hop evidence. Derived queries are deduplicated and bounded; every executed hop records query, retrieval query, expansions, candidate IDs, hybrid fingerprint, and latency.

The committed integration fixture uses an injected deterministic planner to prove two-hop mechanics on non-adjacent legal chunks. Rule-gating behavior is tested independently in unit tests.

## Verification contract

Phase 9 keeps all previous gates and adds:

- reranker contract/order tests;
- mocked Cohere request/response parsing;
- bounded 429 retry/backoff and timeout exhaustion tests;
- rerank-order-change and provenance-preservation integration coverage;
- simple-query non-trigger regression;
- non-adjacent two-hop recovery fixture;
- real local Qdrant + BM25 end-to-end retrieval through RRF, rerank, and top-5 final context;
- machine-readable `scripts/retrieval_service_fixture_report.py` evidence;
- full cumulative regression and dedicated installed-Tesseract OCR.

Canonical commands remain:

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
python scripts/retrieval_service_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated OCR remains a separate installed-Tesseract job.

## Completion criteria

Phase 9 is complete only after the exact final PR head passes all three CI jobs, PR #9 is merged, the merge commit independently passes the same three jobs on `main`, closure documentation is updated to the actual merge/run evidence, and the final documentation handoff head is green again.

Live Cohere validation is an additional credential-dependent tier. Its absence must remain explicitly recorded rather than being converted into a pass.
