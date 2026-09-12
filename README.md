# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is to make retrieval and generation quality measurable, reproducible, and debuggable.

## Current status

Phases 1–7 are merged and verified on `main`. Phase 8 concurrent hybrid retrieval is implemented and accepted on PR #8, with merge/post-merge closure still pending. The current pipeline covers repository/quality foundations, deterministic corpus governance, normalized PDF/DOCX/HTML loading with explicit OCR fallback, provenance-preserving cleaning, interchangeable chunking strategies, reproducible dense retrieval over versioned Qdrant collections, deterministic BM25/BM25+ lexical retrieval, and rank-based hybrid fusion over the same canonical chunk identities.

Phase 6 dense retrieval consumes canonical Phase 5 chunks, embeds them behind a replaceable provider boundary, preserves stable chunk/configuration/provenance identity in reconstructable Qdrant payloads, and returns the canonical `RetrievalResult` contract. The deterministic/local acceptance path uses a local hashed embedding adapter for mechanics and real-Qdrant integration only; live OpenAI validation remains unrun without credentials.

Phase 7 sparse retrieval implements BM25/BM25+ with a conservative domain-aware tokenizer. It preserves exact forms such as `10-K`, `Q3`, ticker symbols, percentages, legal clause/section references, acronyms, `BM25+`, and hyphenated technical terms. Sparse search supports domain, document, source-date, and chunking-configuration filters, deterministic index/configuration fingerprints, snapshot save/load integrity checks, and diagnostics for query tokens, matched terms, rank, score, and matched-term frequency.

Phase 8 composes dense and sparse retrieval concurrently and fuses their 1-based rankings with Reciprocal Rank Fusion using the reference default `k=60`. It preserves dense/sparse ranks and raw scores as diagnostics instead of directly normalizing incompatible score spaces. Hybrid search applies the same metadata filters to both branches and can optionally add bounded observable query expansions behind an async provider interface. The deterministic acceptance path uses a dictionary expansion adapter and always retains the original query.

The small committed fixtures verify mechanics, provenance, exact lexical recovery, RRF arithmetic, async coordination, and expansion behavior rather than production retrieval quality. The accepted local fixture timing did not show a concurrency speedup, so no fixed latency-improvement claim is made.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
make verify
make integration
make dense-report
make sparse-report
make hybrid-report
make smoke
```

Inspect a corpus without parsing document contents:

```bash
python -m rageval.corpus.cli scan ./data/raw --output ./data/corpus-manifest.json
python -m rageval.corpus.cli validate ./data/corpus-manifest.json --root ./data/raw
```

Parse one source into normalized debug JSON without indexing:

```bash
python -m rageval.ingestion.cli file ./data/raw/development/financial/report.pdf \
  --domain financial --output ./tmp/report.elements.json
```

Parse a manifest subset:

```bash
python -m rageval.ingestion.cli corpus ./data/corpus-manifest.json \
  --root ./data/raw --output-dir ./tmp/elements --split development
```

Parse, clean, and chunk one source without indexing:

```bash
python -m rageval.chunking.cli ./data/raw/development/financial/report.pdf \
  --domain financial --strategy fixed_512 --output ./tmp/report.chunks.json
```

For offline semantic mechanics/debugging, the Phase 5 semantic CLI uses the deterministic local hashed embedding adapter rather than claiming a hosted or learned semantic-model result:

```bash
python -m rageval.chunking.cli ./data/raw/evaluation/research/paper.html \
  --domain research --strategy semantic --output ./tmp/paper.semantic-chunks.json
```

Query a persisted sparse snapshot with lexical diagnostics:

```bash
python -m rageval.retrieval.sparse.cli ./tmp/sparse-index.json "Section 7.4" \
  --domain legal --top-k 20
```

Reproduce the deterministic fixture evidence used by CI:

```bash
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
python scripts/dense_fixture_report.py
python scripts/sparse_fixture_report.py
python scripts/hybrid_fixture_report.py
```

The dense fixture report starts from the committed source fixtures, parses/cleans/chunks them, indexes them in a real local Qdrant container, verifies consistency and filters, performs canonical retrieval sanity checks, emits machine-readable JSON, and deletes its temporary collection.

The sparse fixture report starts from the same committed source fixtures, parses/cleans/chunks them, builds the deterministic BM25+ index, verifies order-independent rebuild and snapshot round-trip identity, performs exact-term lexical retrieval checks with provenance intact, and emits machine-readable JSON.

The hybrid fixture report indexes the same canonical chunks into real local Qdrant and BM25, runs concurrent RRF retrieval, verifies lexical and vocabulary-mismatch paths, records branch/fusion diagnostics, and measures concurrent versus sequential local timing without asserting that concurrency must be faster.

The corpus layout is `<root>/<development|evaluation>/<financial|legal|research>/<file>`.
Supported discovery/parsing formats are PDF, DOCX, HTML, and HTM.

## Architecture principles

- Hosted services are adapters behind explicit protocols, never hard-wired dependencies.
- Deterministic tests are the acceptance baseline; live-provider checks are an additional tier.
- Benchmark and evaluation numbers must come from actual runs, never from documentation constants.
- Evaluation sources must remain held out by identity and checksum, including renamed duplicates.
- Parser libraries never leak raw objects beyond the ingestion boundary.
- OCR fallback is explicit, configurable, observable, and separately validated with a real local Tesseract path.
- Cleaning is configuration-fingerprinted, auditable, and conservative about deleting repeated answer-bearing body content.
- Chunking consumes cleaned elements, preserves table/source provenance, and fingerprints every behavior-affecting configuration.
- Dense indexing preserves canonical chunk IDs/configuration/provenance, validates collection schemas before reuse, and keeps external embeddings behind replaceable providers.
- Sparse indexing preserves the same canonical chunk identity, fingerprints scoring/tokenization behavior, and keeps filter semantics explicit rather than rebuilding corpus statistics per query.
- Hybrid retrieval fuses dense and sparse **ranks** by canonical identity with deterministic RRF; incompatible raw score spaces remain independently auditable diagnostics rather than being naïvely normalized or added.
- Query expansion is optional, bounded, observable, provider-abstracted, and cannot remove the original query.
- Local-hash dense evidence and tiny sparse/hybrid fixtures validate mechanics, not learned semantic quality or production retrieval quality.
- No chunking or retrieval strategy is considered preferable without representative evaluation evidence.
- Every phase must pass its own tests and the cumulative regression suite before completion.

Phase 9 — reranking and multi-hop retrieval service — is next after Phase 8 merge closure.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, `docs/phases/`, and `docs/plans/`.
