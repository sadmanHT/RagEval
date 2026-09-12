# Phase 8 Plan — Concurrent Hybrid Retrieval, Reciprocal Rank Fusion & Query Expansion

## Mission

Combine the existing Phase 6 dense-Qdrant and Phase 7 BM25/BM25+ retrievers behind one diagnosable hybrid retrieval path. Preserve canonical chunk identity and branch-specific evidence, fuse rankings with deterministic Reciprocal Rank Fusion, and make bounded query expansion optional and observable.

This phase follows the project rule: measure first, optimize second. Fixture results prove mechanics and regression safety; they do not establish production retrieval quality or a preferred provider/model.

## Required behavior

- run dense and sparse search concurrently where APIs permit;
- request the reference top 20 from each branch;
- fuse with 1-based `1 / (k + rank)` Reciprocal Rank Fusion, default `k=60`;
- deduplicate canonical chunk IDs without double-counting a branch;
- retain dense/sparse ranks, raw branch scores, RRF contributions, final rank, and branch/total latency;
- apply domain, document, source-date, and chunking-config filters consistently to both branches;
- support optional query expansion behind an interface;
- provide a deterministic dictionary/rule expansion baseline for CI;
- retain the original query, bound expansion count/length, and deduplicate expansions;
- propagate cancellation and branch failures instead of swallowing them;
- provide a sequential diagnostic path only for measured local concurrent-vs-sequential timing evidence;
- never normalize or add dense cosine and BM25 scores directly.

## Acceptance tests

- RRF arithmetic, 1-based ranks, overlaps, ties, duplicates, missing branches, and stable ordering;
- canonical chunk-ID collision protection;
- async proof that both branches are started and awaited concurrently;
- sibling cancellation and typed error propagation on branch failure;
- equivalent filter propagation;
- expansion bounds/dedup/original-query retention;
- dense-only and sparse-only result paths;
- latency instrumentation without result nondeterminism;
- real local-Qdrant + BM25 integration over the same committed canonical chunks;
- lexical-exact, natural-language dense-path mechanics, and deterministic vocabulary-mismatch fixture queries;
- permanent hybrid fixture evidence plus every Phase 1–7 cumulative gate.

## Completion gate

Phase 8 is complete only when one hybrid call returns provenance-rich correctly fused results from both indexes, the exact final PR head passes quality/integration/full-regression/installed-OCR CI, the PR is merged without head movement, and the resulting `main` commit independently repeats the full three-job suite.

## Phase 9 handoff

Phase 9 should consume the fused candidate list and add reranking/multi-hop retrieval behind provider abstractions. It must preserve Phase 8 branch/fusion diagnostics and canonical chunk IDs rather than replacing RRF evidence with reranker scores.
