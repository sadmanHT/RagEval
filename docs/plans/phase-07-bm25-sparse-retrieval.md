# Phase 7 Implementation Plan — BM25 Sparse Retrieval

## Mission

Implement an independently useful lexical retrieval path over canonical Phase 5 chunks so exact terminology, identifiers, ticker symbols, clause references, acronyms, percentages, and domain vocabulary can be recovered without depending on dense semantic similarity.

## Preconditions

- Start from the fully verified Phase 6 `main` handoff.
- Reuse canonical `Chunk` and `RetrievalResult` contracts.
- Preserve dense/Qdrant behavior and cumulative Phase 1–6 gates.
- Do not claim retrieval-quality improvements from fixture mechanics alone.

## Implementation boundary

1. Add a common result-only `Retriever.retrieve(query, top_k=20)` protocol while leaving provider-specific rich search responses intact.
2. Implement deterministic BM25 and BM25+ scoring without introducing an unnecessary external lexical-index dependency.
3. Add a conservative domain-aware tokenizer that preserves financially, legally, and technically meaningful lexical forms.
4. Build versioned sparse-index configuration, deterministic order-independent fingerprints, persisted snapshots, and integrity validation.
5. Support domain, document, source-date, and chunking-configuration filters while retaining fixed global corpus statistics for scoring.
6. Return canonical `RetrievalResult` objects with original chunk identity/provenance untouched.
7. Add diagnostics for query tokens, matched terms, term frequency, rank, and score.
8. Add a machine-readable fixture evidence command and permanent CI gate.

## Tokenization policy

The tokenizer deliberately uses a small conservative stopword set rather than broad language stopword removal. It preserves forms such as:

- `10-K`, `10-Q`, `Q1`–`Q4`, `$AAPL`, `BRK.B`, percentages, EPS, EBITDA;
- `Section 7.4`, `§12.2`, NDA/MSA terminology, and hyphenated legal terms;
- acronyms, `BM25+`, `RRF`, equation/figure references, and hyphenated technical vocabulary.

Lowercasing is deterministic and configuration-owned. Tokenizer behavior participates in sparse-index configuration identity.

## Index identity and persistence

- Sparse configuration has schema and index versions.
- Configuration fingerprint includes variant, BM25 parameters, default top-k, and tokenizer configuration.
- Index fingerprint includes the configuration fingerprint plus deterministically ordered canonical chunks, domains, dates, and token streams.
- Rebuilding the same corpus in a different input order must produce the same index fingerprint.
- JSON snapshot loading recomputes and validates configuration fingerprint, index fingerprint, document frequencies, average document length, and document count.

## Filtering semantics

Filters are eligibility filters over an index whose BM25 document frequencies and average document length remain global and fixed. Applying a domain/document/date/chunk-config filter does not silently rebuild or renormalize corpus statistics, preserving comparable rank semantics within one index version.

## Verification

Required acceptance evidence:

- financial/legal/research tokenization goldens;
- exact lexical hit where a deterministic fake dense retriever misses;
- controlled term-frequency/document-length ranking;
- filter and empty-query behavior;
- deterministic rebuild and persistence fingerprint checks;
- Phase 5 chunk-to-sparse integration with provenance intact;
- machine-readable sparse fixture evidence;
- retained real-Qdrant dense evidence;
- complete unit, integration, smoke, static, full-regression, and installed-Tesseract OCR gates.

## Completion rule

Phase 7 is complete only after the final PR head and merged `main` revision independently pass all cumulative gates. Fixture scores are mechanics evidence, not a benchmark or proof that BM25/BM25+ is superior to dense retrieval.
