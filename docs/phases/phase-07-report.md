# Phase 7 Report — BM25 Sparse Index, Domain Tokenization & Lexical Retrieval

## Status

Phase 7 is complete, merged, and independently revalidated on `main`.

Final validated PR head: `2845b6f1d5bda03d7f15a0123d1c7a827df00546`.
Final PR-head GitHub Actions run: `34712500651` — quality, integration, and dedicated local OCR all passed.
PR #7 merged as commit `ec7235fd1584b6f6d35cec040cb061969991e766`.
Post-merge `main` GitHub Actions run: `34712603029` — quality, integration with cleaning/chunking/dense/sparse evidence and full regression, and dedicated installed-Tesseract OCR all passed.

The earlier implementation-acceptance head `931c1b06aa670e62dac7695d1a99df4c225ffffa` remains the source of the exact detailed test-count evidence below; the final PR head and merge commit repeated the complete three-job gate without changing implementation behavior.

## Mission delivered

Phase 7 adds an independently useful deterministic lexical retrieval path over canonical Phase 5 chunks. It supports BM25 and BM25+, conservative domain-aware tokenization, top-k retrieval, metadata filtering, deterministic/persisted sparse-index identity, term-level diagnostics, and the existing canonical `RetrievalResult` contract.

The implementation does not claim that sparse retrieval is globally better than dense retrieval. The committed fixtures verify mechanics, exact lexical recovery, identity, provenance, filters, scoring behavior, and rebuild determinism. Representative retrieval-quality comparison remains a later evaluation task.

## Architecture decisions

### Common retriever boundary

A result-only `Retriever` protocol now exposes `retrieve(query, top_k=20)`. `BM25SparseIndex` satisfies it directly. Phase 6 `QdrantDenseIndex.search()` remains unchanged; a thin `DenseRetriever` adapter exposes dense results through the common protocol without breaking the richer dense response contract.

This keeps Phase 8 fusion able to consume dense and sparse `RetrievalResult` sequences keyed by canonical `chunk_id`, while retaining provider-specific filters and diagnostics outside the lowest-common-denominator interface.

### Tokenization

`DomainAwareTokenizer` uses deterministic regular-expression tokenization with a deliberately small stopword set. It preserves domain-significant forms such as:

- financial: `10-K`, `10-Q`, `Q3`, `$AAPL`, `BRK.B`, percentages, EPS, EBITDA;
- legal: dotted clause numbers, `§` references, NDA/MSA terminology, hyphenated terms;
- research/technical: acronyms, `BM25+`, `RRF`, equation/figure references, and hyphenated technical terms.

Financial/legal/research protected vocabulary avoids accidental removal when conservative stopword handling is enabled. Lowercasing and stopword behavior are configuration-owned and included in sparse-index identity.

### BM25/BM25+ scoring

The implementation is dependency-light and auditable rather than wrapping a separate BM25 library. Default scoring is BM25+ with:

- `k1 = 1.2`
- `b = 0.75`
- `delta = 1.0`
- default `top_k = 20`

Plain BM25 is also supported. IDF uses the indexed corpus-wide document frequencies, term frequency is length-normalized, query-term frequency participates in scoring, and equal-score results use canonical `chunk_id` as a stable secondary ordering key.

### Filters and rank semantics

Domain, document ID, source-date range, and chunking-configuration filters are applied as eligibility filters over fixed global sparse-index statistics. The implementation does not silently recompute document frequencies or average document length per filter, avoiding query-dependent index semantics.

### Deterministic sparse index and persistence

Sparse configuration and snapshots are typed/versioned. The configuration fingerprint covers all scoring/tokenization behavior. The index fingerprint covers the configuration plus deterministically ordered canonical chunk content, domains, dates, and token streams.

Input document/chunk order therefore does not alter index identity. JSON snapshot loading recomputes and validates configuration fingerprint, index fingerprint, document frequencies, average document length, and document count before accepting the snapshot.

### Diagnostics

Rich sparse search responses include:

- normalized query tokens;
- canonical retrieval results and ranks;
- matched terms;
- matched-term frequencies;
- BM25/BM25+ scores;
- sparse index/config fingerprints and index version;
- active filters and measured total query latency.

A diagnostic CLI can query a persisted sparse snapshot and emit that information as JSON.

## Files changed

Production/configuration:

- `.github/workflows/ci.yml`
- `Makefile`
- `src/rageval/core/protocols.py`
- `src/rageval/retrieval/dense/__init__.py`
- `src/rageval/retrieval/dense/retriever.py`
- `src/rageval/retrieval/sparse/__init__.py`
- `src/rageval/retrieval/sparse/bm25.py`
- `src/rageval/retrieval/sparse/cli.py`
- `src/rageval/retrieval/sparse/models.py`
- `src/rageval/retrieval/sparse/tokenizer.py`
- `scripts/sparse_fixture_report.py`

Tests:

- `tests/unit/test_sparse_retrieval.py`
- `tests/integration/test_sparse_retrieval.py`
- `tests/unit/test_imports.py`

Documentation:

- `docs/plans/phase-07-bm25-sparse-retrieval.md`
- this report
- README and implementation-state handoff updates

## Required behavior tests

Unit coverage includes:

- financial tokenizer golden preserving `10-K`, `Q3`, `$AAPL`, `BRK.B`, `12.5%`, and `EBITDA`;
- legal tokenizer golden preserving `Section 7.4`, `§12.2`, `non-compete`, and NDA;
- research tokenizer golden preserving `RRF`, `BM25+`, `cross-encoder`, and equation references;
- invalid reversed date range rejection;
- exact `ZX-91` lexical retrieval when a deterministic fake dense retriever returns no result;
- runtime conformance to the common `Retriever` protocol;
- controlled term-frequency/document-length ranking behavior;
- domain/document/date/chunk-config filters;
- empty-query behavior;
- order-independent rebuild fingerprint;
- configuration changes affecting index identity;
- snapshot round-trip preserving results;
- tampered snapshot fingerprint rejection.

Integration coverage starts at the committed source fixtures and executes manifest -> parser -> cleaner -> Phase 5 fixed-512 chunker -> BM25+ sparse index -> query. It verifies canonical chunk equality, chunk ID/config fingerprint, source-element provenance, matched terms, and sparse retriever identity.

## Accepted verification evidence

Accepted implementation head:
`931c1b06aa670e62dac7695d1a99df4c225ffffa`

GitHub Actions run:
`34712367240`

Quality job:

- Python 3.11.16
- `ruff check .` — passed
- `ruff format --check .` — passed; 100 files already formatted
- `mypy src` — passed; no issues in 46 source files
- `pytest -q tests/unit` — 90 passed in 1.29s

Integration job:

- `docker compose config` — passed
- Qdrant `qdrant/qdrant:v1.10.1` and Redis `7.2-alpine` started successfully
- readiness — `qdrant and redis are ready`
- `pytest -q tests/integration` — 25 passed, 1 skipped in 1.97s
- sole skip — inherited local-OCR-only test because Tesseract is intentionally absent from the ordinary integration runner
- Phase 4 cleaning fixture evidence — passed
- Phase 5 chunking fixture ablation — passed
- Phase 6 real-Qdrant dense fixture evidence — passed
- Phase 7 sparse BM25 fixture evidence — passed
- package smoke — `rageval smoke: ok (development)`
- full `pytest -q` — 115 passed, 1 skipped in 1.95s
- `docker compose down -v` — passed

Dedicated local OCR job:

- installed Tesseract 5.3.4
- `pytest -q -m local_ocr tests/integration/test_local_ocr.py` — 1 passed in 0.61s

Final PR and post-merge closure evidence:

- final PR head `2845b6f1d5bda03d7f15a0123d1c7a827df00546`
- final PR-head run `34712500651` — quality, integration, local-ocr all successful
- merge commit `ec7235fd1584b6f6d35cec040cb061969991e766`
- post-merge `main` run `34712603029` — quality, integration, local-ocr all successful
- the integration job on the merge commit retained cleaning fixture stats, chunking ablation, real-Qdrant dense fixture evidence, sparse BM25 fixture evidence, package smoke, full regression, and clean teardown

## Machine-readable sparse fixture evidence

Command:

```bash
python scripts/sparse_fixture_report.py
```

Accepted-run evidence:

- corpus fingerprint: `cba5fea59f8d977e403fa66dd29bc7e282d040a183946b830652ab71af262927`
- index version: `ci_v1`
- index fingerprint: `d93b6989100b8454199f41d6f2c2fb71e9ec78407fcdcaac1e599b7c7812787b`
- sparse configuration fingerprint: `182ae8220080013968bc169182748b3e67ec04e7e1ccca675cbe5ac941a9152c`
- variant: `bm25_plus`
- tokenizer: `domain-aware-lexical-v1`
- `k1=1.2`, `b=0.75`, `delta=1.0`, default top-k `20`
- chunk strategy: `fixed_512`
- source documents: 4
- indexed canonical chunks: 6
- financial/legal/research chunk counts: 3/2/1
- average sparse document length: 14.5 tokens
- rebuild with reversed source-input order produced the same index fingerprint
- persisted snapshot round-trip produced the same index fingerprint

Deterministic exact-term fixture queries all recovered the intended canonical chunk at rank 1:

- financial report query `16.9` -> expected chunk, score `2.9424478028933416`
- legal MSA query `7.2` -> expected chunk, score `2.9424478028933416`
- financial table query `110` -> expected chunk, score `2.9793966311730364`
- research HTML query `calibration` -> expected chunk, score `2.9424478028933416`

Those scores are controlled lexical mechanics evidence chosen from terms unique in the tiny committed fixture index. They are not a production ranking benchmark and must not be compared directly with dense cosine scores.

## Dense-regression evidence retained

The same accepted run repeated Phase 6 real-Qdrant fixture evidence over 4 documents / 6 points with the existing local-hash diagnostic embedding provider and exact-source-text sanity queries. Phase 7 therefore did not replace, bypass, or mutate dense-index behavior.

## Failure and repair history

Phase 7 was not declared successful on its first working runtime path:

1. Initial PR run `34711734572` passed integration, sparse evidence, dense/Qdrant regression, full regression, and real OCR, while quality stopped at Ruff on an unused import, long lines, and import formatting.
2. Run `34711822907` retained green runtime evidence but Ruff still flagged import ordering.
3. Run `34711987664` again retained runtime behavior while the same I001 import issue remained.
4. A temporary diagnostic run `34712114724` used Ruff's own auto-fix inside the ephemeral Actions checkout solely to print its expected diff. It showed one extra blank line in the import block. The diagnostic workflow change was immediately removed and the normal immutable `ruff check .` gate restored.
5. Run `34712170296` passed lint and then exposed two canonical Ruff-format changes; those exact layout changes were applied.
6. Run `34712240402` passed lint/format and exposed one strict-mypy issue: a `Domain | None` value was passed to a `dict[Domain, ...]` lookup. The code now narrows `None` explicitly; no `type: ignore` was added.
7. Run `34712323276` reached the repaired type boundary but formatter required the narrowed conditional expression on one line. The exact Ruff layout was applied.
8. Run `34712367240` reran the complete cumulative suite and passed all three jobs.

No tests, assertions, lint rules, formatting gates, strict typing, dense-Qdrant evidence, cleaning/chunking evidence, full regression, or installed-Tesseract OCR checks were weakened.

## Provider validation

Phase 7 requires no external hosted provider. Sparse retrieval is deterministic and local. Phase 6 hosted OpenAI validation remains separately unrun without credentials; Phase 7 neither changes nor upgrades that status.

## Known limitations

- The sparse acceptance corpus is four source documents producing six canonical chunks, not the target ~12,000-document corpus. No scale or retrieval-quality claim is made.
- The tokenizer is deliberately conservative and regex-based. Domain stopwords/token forms will need representative-corpus evaluation before claiming optimality.
- Sparse snapshots are JSON and suitable for deterministic reproducibility/debugging, not a claimed production distributed lexical-index format.
- Filters retain global corpus statistics rather than recomputing BM25 statistics for each filtered subset; this behavior is explicit and deterministic.
- No stemming, lemmatization, synonym expansion, typo tolerance, phrase index, or learned sparse encoder is included in Phase 7.
- Fixture term queries intentionally use unique lexical evidence and do not estimate recall, context precision, or user-query performance.
- BM25 and dense scores are intentionally not normalized against each other. Phase 8 should fuse rankings by rank/identity, not raw score arithmetic.
- GitHub Actions emits a non-failing Node-action deprecation warning from current checkout/setup-python action versions.

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
python scripts/sparse_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated OCR validation remains:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

with Tesseract installed in its dedicated CI job.

## Phase 8 handoff

Phase 8 should combine the existing dense and sparse retrievers by canonical `chunk_id` using Reciprocal Rank Fusion with the reference smoothing constant `k=60`, while preserving each retriever's original rank/score diagnostics. Raw BM25 and cosine scores must not be naïvely normalized or added. Query expansion, if included by the Phase 8 contract, should remain explicit/configurable and evaluation-backed. The Phase 7 sparse fixture scores are not quality benchmarks and must not be used to claim hybrid improvement without representative evaluation evidence.
