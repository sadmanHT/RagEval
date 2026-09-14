# RAG-Eval

RAG-Eval is a production-oriented Retrieval-Augmented Generation system whose primary goal is to make retrieval and generation quality measurable, reproducible, and debuggable.

## Current status

Phases 1–14 are merged and verified on `main`. The pipeline now covers repository/quality foundations, deterministic corpus governance, normalized PDF/DOCX/HTML loading with explicit OCR fallback, provenance-preserving cleaning, interchangeable chunking, reproducible dense Qdrant retrieval, deterministic BM25/BM25+ sparse retrieval, RRF hybrid fusion, a reranked retrieval-service layer with bounded multi-hop over the same canonical chunk identities, provider-abstracted grounded generation with deterministic context assembly/citation validation/refusal, leakage-aware evaluation dataset/metric/judge contracts, a resumable comparative-evaluation runner with configuration matrices/regression policies/experiment tracking/reporting/failure analysis, a typed async FastAPI serving boundary, sanitized operational tracing, low-cardinality Prometheus metrics, provisioned Grafana dashboards, containerized operational smoke/outage testing, scheduled evaluation semantics, dependency/secret scanning, and serving abuse/security controls. The next work is production deployment/platform hardening and representative validation when the real corpus/evaluation set and required provider credentials are available.

Phase 6 dense retrieval consumes canonical Phase 5 chunks, embeds them behind a replaceable provider boundary, preserves stable chunk/configuration/provenance identity in reconstructable Qdrant payloads, and returns the canonical `RetrievalResult` contract. The deterministic/local acceptance path uses a local hashed embedding adapter for mechanics and real-Qdrant integration only; live OpenAI embedding validation remains unrun without credentials.

Phase 7 sparse retrieval implements BM25/BM25+ with a conservative domain-aware tokenizer and stable filters, deterministic index/configuration fingerprints, snapshot integrity checks, and lexical diagnostics.

Phase 8 composes dense and sparse retrieval concurrently and fuses their 1-based rankings with Reciprocal Rank Fusion using the reference default `k=60`. Dense and sparse raw scores remain independently auditable rather than being normalized or added. Optional query expansion is bounded, observable, provider-abstracted, and cannot remove the original query.

Phase 9 consumes Phase 8 candidates through a provider-abstracted reranking engine and returns a default final top-5 context while preserving the nested original retrieval result, canonical IDs, provenance, pre/post rerank ranks, rerank score, provider/model identity, and configuration fingerprint. The hosted reference adapter targets Cohere Rerank with bounded timeout/retry/backoff behavior; deterministic acceptance uses a local fake reranker, and Cohere HTTP behavior is covered with mocked request/response, 429, and timeout tests. Live Cohere validation was not run without credentials, and no local neural cross-encoder is currently implemented.

The retrieval service also supports bounded multi-hop retrieval. Multi-hop is `off` by default, can be explicitly enabled, or can use a conservative rule planner that requires relationship cues plus an explicit section/clause/appendix/schedule reference. Every executed hop records its query, retrieval query, expansion state, candidate IDs, hybrid configuration fingerprint, and branch/total latency before merged candidates are reranked.

Phase 10 consumes Phase 9 `final_context` directly. `ContextAssembler` deterministically orders reranked chunks, suppresses duplicates/near-duplicates, records chunk/source metadata, enforces a context budget, and fingerprints its behavior. Retrieved document text is rendered as untrusted context data rather than system instructions. Structured generation output is validated application-side: non-refusal citations must reference supplied canonical chunk IDs, malformed output or invalid citations may use a bounded auditable repair step, and insufficient-context responses must refuse without supporting citations.

The credential-free generation acceptance path uses `DeterministicFakeGenerationProvider`. The hosted reference adapter targets OpenAI and implements bounded timeout/retry/backoff plus strict structured response/usage parsing; its HTTP behavior is covered with deterministic mocked 429 and timeout tests. No live OpenAI generation is claimed without credentials. `AlwaysRetrieveRouter` is the default; an opt-in conservative Self-RAG-style router exposes its decision, and any no-retrieval route currently refuses rather than emitting an ungrounded answer under the same grounded-answer guarantee.

Phase 11 finalizes held-out evaluation-example governance, strict JSONL/review tooling, corpus-fingerprint and held-out document leakage checks, canonical chunk-ID context precision/recall, structured provider-abstracted judge contracts, deterministic rule/scripted judges, claim-level faithfulness, answer relevancy, and response-level hallucination defined strictly as `faithfulness < 0.8`. Evaluation runs carry deterministic dataset/config/run fingerprints, and hallucination output persists the flagged count, total count, threshold, and arithmetically validated `count / N` rate.

Phase 12 consumes those contracts through `AsyncEvaluationRunner`: bounded concurrency, retries/backoff, atomic per-example checkpoints/resume, deterministic configuration/matrix/run fingerprints, overall and financial/legal/research metric slices with sample counts, the required failure taxonomy, PR-fast versus nightly regression semantics, reuse of the existing experiment-tracker abstraction, credential-free local JSON tracking, optional W&B, and JSON/Markdown/HTML comparative reports. The permanent CI fixture runs five distinct configurations across fixed-256/512/1024, semantic, and table-aware chunk labels with query-expansion/multi-hop toggles, but the resulting differences are mechanics fixtures only and are not used to select a production strategy.

Phase 13 exposes the canonical Phase 9–12 retrieval/generation/evaluation stack rather than rebuilding it behind HTTP. `/query` supports typed question/domain/filter/`top_k` options, API-key authentication, request IDs, body/time/concurrency limits, grounded cited answers, optional retrieval diagnostics, correctness-scoped Redis caching, and NDJSON transport streaming with a final structured citation event. `/health/live` and `/health/ready` separate process liveness from dependency readiness. `/eval/run`, `/eval/jobs/{job_id}`, and `/eval/latest` use a fixed-worker bounded in-process queue. Unexpected request, streaming, and evaluation-worker failures return safe generic errors and do not log arbitrary downstream exception strings. The real-local acceptance path uses Qdrant + Redis with deterministic providers and is explicitly mechanics/grounding/traceability evidence, not a production serving benchmark.

Phase 14 instruments that same serving/evaluation boundary rather than creating a parallel operational path. Query/evaluation traces are Langfuse-compatible and sanitized by construction: raw document/context text is never exported, raw query text is off by default, and rank/RRF/rerank/context/citation/provider/token/latency evidence remains observable. Prometheus exposes bounded-cardinality request/error/stage/cache/provider/token/cost/evaluation/dependency metrics, Grafana is provisioned from source control, and drift hooks retain bounded query-length/embedding-norm aggregates with explicit insufficient-data handling. The runtime image is non-root, the Compose stack covers API/Qdrant/Redis/Prometheus/Grafana, PR CI builds and tests the stack from clean volumes, the full repository suite runs inside the Tesseract-enabled test image, and an actual Qdrant outage must produce readiness degradation plus a dependency metric. PR-fast evaluation remains a pre-merge blocker while scheduled/manual evaluation is alert/report-only. Dependency auditing, secret scanning, Dependabot, exact-origin CORS defaults, bounded security headers, response hardening, and a hashed per-process rate limiter complete the Phase 14 operational baseline.

The target roughly 200-question evaluation set and representative roughly 12,000-document corpus are not present and were not fabricated. Phase 11/12 deterministic acceptance uses three reviewed synthetic financial/legal/research records, Phase 13 serving acceptance uses the committed four-document/six-chunk fixture path, and Phase 14 adds deterministic operational/container fixtures rather than representative workloads. The lexical rule judge, optional injected-scorer RAGAS adapter, deterministic observation/serving providers, and Phase 14 local operational stack validate measurement/orchestration/schema/arithmetic/serving/operations mechanics only; no live LLM judge, actual RAGAS-backed semantic result, representative ablation winner, hosted-provider quality result, production load/SLO/cost result, or statistically significant drift result is claimed.

The small committed fixtures verify mechanics, provenance, deterministic ordering, retry/error handling, top-5 orchestration, two-hop recovery, context budgeting, citation traceability, bounded repair, prompt-boundary behavior, explicit refusal, metric arithmetic, judge schema auditing, run fingerprinting, resumable evaluation, regression semantics, report generation, failure classification, authenticated serving, cache identity/invalidation, streaming citation preservation, readiness degradation, bounded evaluation jobs, sanitized telemetry, metric-cardinality controls, non-root container execution, clean-stack startup, security scanning, and dependency-outage observability rather than production retrieval/generation/evaluation quality. No neural-reranking quality, hosted-model answer quality, target-corpus retrieval improvement, representative faithfulness/hallucination/answer-relevancy score, production ablation winner, production load result, or production latency/cost benchmark is claimed from these fixtures.

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
make evaluation-report
make evaluation-gate
make evaluation-ablation-report
make serving-report
make smoke
```

Start and verify the Phase 14 operational stack:

```bash
export RAGEVAL_SERVING_API_KEY=replace-this-local-key
make docker-build
make ops-smoke
make container-test
make ops-down
```

See `docs/operations.md` for Prometheus/Grafana, external Langfuse, scheduled evaluation, outage drills, security boundaries, and recovery guidance.

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
python scripts/evaluation_fixture_report.py
python scripts/evaluation_gate.py --mode pr
python scripts/evaluation_ablation_fixture_report.py
python scripts/serving_fixture_report.py
```

The dense fixture report uses real local Qdrant; the sparse report validates deterministic BM25+ identity and exact-term retrieval; the hybrid report validates concurrent RRF mechanics and bounded expansion; the retrieval-service report validates top-5 reranking plus bounded two-hop recovery; the generation report validates retrieval-to-context-to-grounded-answer citation traceability plus explicit unsupported-question refusal; the evaluation report validates deterministic metric arithmetic, hallucination count/rate consistency, structured judge/version metadata, and dataset/config/run fingerprints; the Phase 12 ablation report validates resumable comparative-run mechanics, distinct configuration fingerprints, per-domain/sample-count aggregation, experiment tracking, failure classification, and JSON/Markdown/HTML reporting; the Phase 13 serving report validates authenticated query/evaluation HTTP contracts, real local Qdrant/Redis readiness, cache hit and index-fingerprint invalidation, bounded job completion, and final streaming citation preservation; and the Phase 14 PR-fast gate validates pre-merge regression-policy mechanics against the committed fixture. All use committed fixtures and emit machine-readable evidence.

The Phase 9 fixture proves deterministic reranking can move a canonical candidate from pre-rerank rank 6 to post-rerank rank 1 while preserving the original retrieval/provenance object. Its multi-hop fixture proves a bounded second hop can recover a non-adjacent legal chunk while retaining both hop traces. These are mechanics fixtures, not retrieval-quality benchmarks.

The Phase 10 fixture builds 6 canonical chunks from 4 committed source documents. Its answerable path cites a canonical chunk ID that is present in the exact supplied assembled context, and its intentionally unanswerable Europa question returns `insufficient_context=true` with zero citations. This proves structured grounding/refusal mechanics only; it does not establish semantic faithfulness or hosted-model quality.

The Phase 11 fixture evaluates 3 reviewed synthetic records. It computes one flagged response out of three at the strict `faithfulness < 0.8` threshold and persists the rate as `1 / 3`; these numbers are mechanics/arithmetic evidence only and are not a production hallucination-rate estimate.

The Phase 12 fixture evaluates the same 3 reviewed synthetic records under 5 deliberately distinct configurations. It verifies that summaries are recomputed from per-example records and that each configuration has distinct run/configuration identity. It is explicitly labeled `deterministic-fixture-ablation-mechanics-only` and does not establish a preferred chunker, retrieval architecture, expansion policy, or multi-hop policy.

The Phase 13 fixture builds 6 canonical chunks from 4 committed source documents behind real local Qdrant and Redis. It verifies authenticated cited query responses, readiness, cache reuse, cache invalidation after index identity changes, final streaming citations, and evaluation-job completion. It is labeled `phase13-serving-fixture-mechanics-only` and does not establish hosted-provider quality, production scale, or SLO performance.

The Phase 14 operational fixture starts API/Qdrant/Redis/Prometheus/Grafana from clean volumes, verifies an authenticated cited query and evaluation job, checks `/metrics`, Prometheus scraping and Grafana health, runs the cumulative suite in a Tesseract-enabled container, and then stops Qdrant to prove HTTP 503 readiness plus `rageval_dependency_ready{component="qdrant"} 0.0`. It is labeled `phase14-container-operational-mechanics-only` and is not a production load or quality benchmark.

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
- Evaluation metric/judge/run contracts must remain versioned and fingerprinted; headline scores must be derived from actual per-example records.
- Hallucination-rate output must retain its numerator and denominator; an independently typed percentage is not accepted as evidence.
- Comparative evaluation must retain dataset/configuration/corpus identities, sample counts, and per-example records; fixture-only differences must not be promoted into production recommendations.
- PR-fast regression gates and nightly/full regression alerts are distinct semantics; post-merge nightly checks are not represented as pre-merge blockers.
- Serving must preserve the canonical retrieval/generation/evaluation contracts, authenticate callers, bound expensive concurrency, and version cache identity with every answer-affecting artifact.
- Streaming must preserve a final structured citation/refusal contract; transport streaming is not represented as provider-native token streaming.
- Generic serving failures must not expose or log arbitrary downstream exception strings that may contain credentials.
- Operational traces must prefer identifiers, fingerprints, ranks, aggregate metadata, and configured redaction over raw document/context content.
- Metric labels must remain bounded; request/job/document/chunk identifiers and user text are not acceptable Prometheus labels.
- Drift indicators are heuristic aggregate signals and must report insufficient-data states rather than claiming significance from tiny samples.
- PR blockers must execute before merge; scheduled/post-merge evaluation is alert/report semantics, not retroactive merge blocking.
- Deterministic/local providers and tiny fixtures validate mechanics, not learned semantic quality, hosted-model answer quality, or production retrieval/generation/evaluation quality.
- No chunking, retrieval, routing, generation, evaluation, serving, or operational strategy is considered preferable without representative evaluation evidence.
- Every phase must pass its own tests and the cumulative regression suite before completion.

See `docs/implementation-state.md`, `docs/architecture-decisions.md`, `docs/operations.md`, `docs/phases/`, and `docs/plans/`.