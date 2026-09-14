# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is to make retrieval and generation quality measurable, reproducible, and debuggable.

## Current status

Phases 1–10 are merged and verified on `main`. The pipeline now covers repository/quality foundations, deterministic corpus governance, normalized PDF/DOCX/HTML loading with explicit OCR fallback, provenance-preserving cleaning, interchangeable chunking, reproducible dense Qdrant retrieval, deterministic BM25/BM25+ sparse retrieval, RRF hybrid fusion, a reranked retrieval-service layer with bounded multi-hop over the same canonical chunk identities, and provider-abstracted grounded generation with deterministic context assembly, citation validation/repair, explicit insufficiency refusal, prompt-injection separation, and observable retrieval routing. Phase 11 — evaluation dataset, metrics, and judge contracts — is next.

Phase 6 dense retrieval consumes canonical Phase 5 chunks, embeds them behind a replaceable provider boundary, preserves stable chunk/configuration/provenance identity in reconstructable Qdrant payloads, and returns the canonical `RetrievalResult` contract. The deterministic/local acceptance path uses a local hashed embedding adapter for mechanics and real-Qdrant integration only; live OpenAI embedding validation remains unrun without credentials.

Phase 7 sparse retrieval implements BM25/BM25+ with a conservative domain-aware tokenizer and stable filters, deterministic index/configuration fingerprints, snapshot integrity checks, and lexical diagnostics.

Phase 8 composes dense and sparse retrieval concurrently and fuses their 1-based rankings with Reciprocal Rank Fusion using the reference default `k=60`. Dense and sparse raw scores remain independently auditable rather than being normalized or added. Optional query expansion is bounded, observable, provider-abstracted, and cannot remove the original query.

Phase 9 consumes Phase 8 candidates through a provider-abstracted reranking engine and returns a default final top-5 context while preserving the nested original retrieval result, canonical IDs, provenance, pre/post rerank ranks, rerank score, provider/model identity, and configuration fingerprint. The hosted reference adapter targets Cohere Rerank with bounded timeout/retry/backoff behavior; deterministic acceptance uses a local fake reranker, and Cohere HTTP behavior is covered with mocked request/response, 429, and timeout tests. Live Cohere validation was not run without credentials, and no local neural cross-encoder is currently implemented.

The retrieval service also supports bounded multi-hop retrieval. Multi-hop is `off` by default, can be explicitly enabled, or can use a conservative rule planner that requires relationship cues plus an explicit section/clause/appendix/schedule reference. Every executed hop records its query, retrieval query, expansion state, candidate IDs, hybrid configuration fingerprint, and branch/total latency before merged candidates are reranked.

Phase 10 consumes Phase 9 `final_context` directly. `ContextAssembler` deterministically orders reranked chunks, suppresses duplicates/near-duplicates, records chunk/source metadata, enforces a context budget, and fingerprints its behavior. Retrieved document text is rendered as untrusted context data rather than system instructions. Structured generation output is validated application-side: non-refusal citations must reference supplied canonical chunk IDs, malformed output or invalid citations may use a bounded auditable repair step, and insufficient-context responses must refuse without supporting citations.

The credential-free generation acceptance path uses `DeterministicFakeGenerationProvider`. The hosted reference adapter targets OpenAI and implements bounded timeout/retry/backoff plus strict structured response/usage parsing; its HTTP behavior is covered with deterministic mocked 429 and timeout tests. No live OpenAI generation is claimed without credentials. `AlwaysRetrieveRouter` is the default; an opt-in conservative Self-RAG-style router exposes its decision, and any no-retrieval route currently refuses rather than emitting an ungrounded answer under the same grounded-answer guarantee.

The small committed fixtures verify mechanics, provenance, deterministic ordering, retry/error handling, top-5 orchestration, two-hop recovery, context budgeting, citation traceability, bounded repair, prompt-boundary behavior, and explicit refusal rather than production retrieval or generation quality. No neural-reranking quality, hosted-model answer quality, target-corpus retrieval improvement, faithfulness score, hallucination rate, answer-relevancy score, or production latency/cost benchmark is claimed from these fixtures.

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
make retrieval-report
make generation-report
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

Reproduce deterministic CI evidence:

```bash
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
python scripts/dense_fixture_report.py
python scripts/sparse_fixture_report.py
python scripts/hybrid_fixture_report.py
python scripts/retrieval_service_fixture_report.py
python scripts/generation_fixture_report.py
```

The dense fixture report uses real local Qdrant; the sparse report validates deterministic BM25+ identity and exact-term retrieval; the hybrid report validates concurrent RRF mechanics and bounded expansion; the retrieval-service report validates top-5 reranking plus bounded two-hop recovery; and the generation report validates retrieval-to-context-to-grounded-answer citation traceability plus explicit unsupported-question refusal. All use committed fixtures and emit machine-readable JSON.

The Phase 9 fixture proves deterministic reranking can move a canonical candidate from pre-rerank rank 6 to post-rerank rank 1 while preserving the original retrieval/provenance object. Its multi-hop fixture proves a bounded second hop can recover a non-adjacent legal chunk while retaining both hop traces. These are mechanics fixtures, not retrieval-quality benchmarks.

The Phase 10 fixture builds 6 canonical chunks from 4 committed source documents. Its answerable path cites a canonical chunk ID that is present in the exact supplied assembled context, and its intentionally unanswerable Europa question returns `insufficient_context=true` with zero citations. This proves structured grounding/refusal mechanics only; it does not establish semantic faithfulness or hosted-model quality.

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
- Hybrid retrieval fuses dense and sparse **ranks** by canonical identity with deterministic RRF; incompatible raw score spaces remain diagnostics rather than being naïvely combined.
- Query expansion is optional, bounded, observable, provider-abstracted, and cannot remove the original query.
- Reranking wraps canonical retrieval results instead of replacing them, so dense/sparse/RRF/expansion evidence remains auditable after post-ranking.
- Multi-hop is bounded and off by default; every executed hop must be traceable and later evaluation must justify broader automatic triggering.
- Grounded generation consumes the canonical reranked context instead of reconstructing retrieval evidence through a parallel path.
- Retrieved document instructions are untrusted data, not system instructions; application-side structured-output and citation validation remains mandatory.
- Generated citations are accepted only when their canonical chunk IDs exist in the context supplied to generation; semantic entailment is a separate evaluation concern.
- Insufficient-context cases must refuse explicitly rather than silently filling gaps with unsupported external knowledge.
- Repair of malformed structured output/citations is bounded and observable; exhaustion fails closed.
- Self-RAG-style routing is observable and retrieval remains the default for domain questions; no-retrieval routes must not silently claim the same faithfulness guarantee.
- Deterministic/local providers and tiny fixtures validate mechanics, not learned semantic quality, hosted-model answer quality, or production retrieval/generation quality.
- No chunking, retrieval, routing, or generation strategy is considered preferable without representative evaluation evidence.
- Every phase must pass its own tests and the cumulative regression suite before completion.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, `docs/phases/`, and `docs/plans/`.
