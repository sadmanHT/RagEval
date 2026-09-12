# Phase 9 Plan — Neural Reranking, Retrieval Service & Multi-hop Retrieval

## Status

Complete. PR #9 merged to `main` as `0cf47f8dc7a2b3ae44c331cb287242c81284ce14` from final validated PR head `28fa30cb6ee3997b02023c6cf2f54c07b8348f69`. Final PR-head GitHub Actions run `34718753817` and independent post-merge `main` run `34718825100` both passed quality, full integration/evidence/regression, and dedicated installed-Tesseract OCR.

## Mission

Turn Phase 8 fused hybrid candidates into a high-precision retrieval-service output by adding a provider-abstracted reranking stage, a default final context size of five, and bounded multi-hop retrieval for queries that genuinely require non-adjacent evidence.

## Preserved contracts

Phase 9 composes, rather than replaces, the existing retrieval stack:

1. parse/clean/chunk contracts remain unchanged;
2. Phase 6 dense Qdrant and Phase 7 BM25/BM25+ continue to own their scoring/index behavior;
3. Phase 8 `HybridRetriever.search()` remains the source of fused `RetrievalResult` candidates and expansion/filter diagnostics;
4. reranking wraps the canonical `RetrievalResult` in the existing `RerankResult` contract so chunk identity and provenance are not reconstructed or discarded.

## Implementation

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

Phase 9 keeps all previous gates and adds reranker contract/order tests, mocked Cohere parsing, bounded 429 retry/backoff and timeout tests, rerank-order/provenance integration coverage, simple-query non-trigger regression, non-adjacent two-hop recovery, real local Qdrant + BM25 + RRF + rerank top-5 evidence, and the machine-readable `scripts/retrieval_service_fixture_report.py` gate.

Canonical commands:

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

Dedicated OCR remains a separate installed-Tesseract job. Live Cohere validation remains an additional credential-dependent tier and was not run in Phase 9.
