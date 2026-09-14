# Phase 10 Report — Grounded Generation, Context Assembly, Citations & Self-RAG Routing

## Status

Phase 10 is complete, merged, and independently revalidated on `main`.

Accepted implementation head: `a249035ea60edf58faf4b84d88043f894e8632e0`.
Accepted implementation GitHub Actions run: `34767396626` — quality, real-service integration/evidence/full regression, and dedicated installed-Tesseract OCR all passed.
Final validated PR head: `ec550e6cb1251f9dbb65894c3adc470fa2dd7456`.
Final PR-head GitHub Actions run: `34806206207` — all three jobs passed after the canonical Phase 10 plan/report and repository-status documentation were added.
PR #10 merged to `main` as commit `87c2c329a12aa4fc3d4a5eb775ed2df32c3ce111`.
Independent merge-triggered `main` GitHub Actions run: `34806319174` — quality, integration with all inherited evidence plus the Phase 10 generation fixture and full regression, and dedicated installed-Tesseract OCR all passed.

No live OpenAI generation result is claimed. Deterministic/local acceptance is complete; hosted request/response/retry/timeout behavior is covered with mocked HTTP.

## Mission delivered

Phase 10 consumes the canonical Phase 9 `RetrievalServiceResponse.final_context` rather than introducing a parallel retrieval path. It deterministically assembles ranked reranked chunks into bounded structured context, treats retrieved text as untrusted document data, invokes generation through a provider boundary, validates structured answers and citations application-side, performs bounded repair when configured, and refuses when evidence is insufficient.

The end-to-end service preserves the Phase 9 retrieval response and augments answer metadata with generation/context configuration fingerprints plus retrieval/rerank/multi-hop diagnostics, so later evaluation can trace a generated answer back through the retrieval pipeline.

## Architecture decisions

### Stable generation contracts

The Phase 1 `GroundedAnswer` contract is extended compatibly with defaulted audit fields rather than replaced. Phase 10 uses answer text, `Citation` objects, cited chunk IDs, provider/model identity, token usage, latency, insufficient-context state, refusal reason, schema version, and metadata. Existing callers that do not populate the new fields remain valid.

A lower-level Phase 10 generation provider protocol lives in `rageval.generation`. This keeps hosted-provider details separate from the repository's higher-level shared contracts while allowing deterministic fake substitution in tests.

### Deterministic context assembly

`ContextAssembler` sorts the Phase 9 reranked context deterministically, preserves canonical chunk IDs and source metadata, inserts explicit chunk separators, applies a configured context-token budget, records included/omitted/duplicate chunk IDs, and performs deterministic truncation when a top-ranked chunk must be shortened to fit.

Near-duplicate content is removed before budgeting so repeated chunks do not consume the context window. Context configuration is fingerprinted and returned with the response for later audit/evaluation.

The current budget counter is intentionally deterministic and credential-free; it is not represented as exact hosted-model tokenizer accounting.

### Prompt-injection boundary

Retrieved chunk text is never concatenated into the system-instruction channel. The system prompt explicitly defines retrieved content as untrusted data and forbids document-supplied instructions from changing grounding/citation rules. Chunk content is rendered in the user/context payload with canonical IDs and source metadata.

The application still validates the model response after generation; prompt wording is not treated as the sole safety/faithfulness control.

### Structured output, citation validation, and bounded repair

The generation engine requires structured JSON-like output that is parsed into typed generation models. For non-refusal answers, cited chunk IDs must be present in the context supplied to the provider. Refusal responses must not carry supporting citations.

Malformed structure, inconsistent refusal state, or nonexistent citations can trigger a bounded repair call. Every repair attempt is recorded with its reason. If the configured repair budget is exhausted, generation fails closed with a typed `GenerationError` instead of silently accepting invalid evidence.

The validator proves citation traceability by canonical chunk ID. It does not yet prove semantic entailment between each claim and cited text; that belongs to the evaluation phase.

### Provider boundary

`DeterministicFakeGenerationProvider` is the credential-free acceptance path. It produces reproducible structured answers and can be scripted to return malformed output, raise provider/timeout errors, or explicitly refuse selected fixture questions.

`OpenAIGenerationProvider` is the hosted reference adapter. It uses `httpx`, configured timeout, bounded attempts, exponential backoff, retryable 429/5xx/network/timeout behavior, structured request/response parsing, provider/model identity, and usage metadata. Unit tests inject `httpx.MockTransport`; no live hosted call was required for acceptance or claimed as executed.

### Self-RAG-style routing

`AlwaysRetrieveRouter` is the default: domain questions retrieve by default. `ConservativeSelfRAGRouter` is opt-in and exposes an observable typed route decision. When routing says retrieval is unnecessary, the current service does not emit an ungrounded domain answer under the same faithfulness guarantee; it returns an explicit insufficient-context refusal with provider/model `none`.

This is a safe mechanics baseline rather than evidence that the heuristic router improves answer quality or cost.

### End-to-end service

`GroundedGenerationService` normalizes the question, obtains the route decision, calls the existing Phase 9 retrieval-service boundary when retrieval is required, passes the final ordered reranked context into `GroundedGenerationEngine`, and returns a `GroundedGenerationResponse` containing the answer, original retrieval response, assembled context, route, repair records, configuration fingerprint, and total latency.

The service retains retrieval-service/rerank fingerprints, hop count, and multi-hop-triggered state in answer metadata instead of flattening or discarding prior diagnostics.

## Files changed

Production:

- `src/rageval/generation/__init__.py`
- `src/rageval/generation/context.py`
- `src/rageval/generation/engine.py`
- `src/rageval/generation/models.py`
- `src/rageval/generation/prompts.py`
- `src/rageval/generation/providers.py`
- `src/rageval/generation/routing.py`
- `src/rageval/generation/service.py`
- `src/rageval/models/contracts.py`

Tests/evidence and CI:

- `tests/unit/test_generation.py`
- `tests/integration/test_grounded_generation.py`
- `scripts/generation_fixture_report.py`
- `.github/workflows/ci.yml`
- `Makefile`

Documentation:

- `docs/plans/phase-10-grounded-generation-citations-self-rag.md`
- this report
- `docs/implementation-state.md`
- `README.md`

## Required behavior tests

Unit coverage verifies:

- deterministic rank ordering and exact duplicate/near-duplicate suppression;
- deterministic context truncation and budget enforcement;
- traceable citation success;
- nonexistent-citation repair;
- malformed-output repair and repair-budget exhaustion;
- explicit insufficient-context refusal with zero citations;
- prompt-injection text staying in the untrusted document channel;
- typed timeout and provider-error failures;
- mocked OpenAI 429 retry then success with structured usage parsing;
- mocked OpenAI timeout exhaustion;
- conservative no-retrieval routing that refuses without invoking retrieval.

The integration test executes fixture parsing -> cleaning -> fixed-512 chunking -> real local Qdrant dense retrieval -> BM25 sparse retrieval -> Phase 8 RRF -> Phase 9 deterministic reranking -> Phase 10 context assembly and grounded generation. It verifies that generated citations are a subset of both the assembled context IDs and the original retrieved final-context IDs, and separately verifies an intentionally unsupported question returns an explicit refusal with no citations.

## Accepted verification evidence

Accepted implementation head: `a249035ea60edf58faf4b84d88043f894e8632e0`

Accepted implementation run: `34767396626`

Quality:

- Python **3.11.16**
- Ruff lint — passed
- Ruff formatter — passed; **135 files already formatted**
- strict mypy — **no issues in 66 source files**
- unit suite — **125 passed in 1.61s**

Integration:

- Docker Compose configuration — passed
- local Qdrant/Redis startup/readiness — passed
- ordinary integration suite — **28 passed, 1 skipped in 3.41s**
- sole ordinary-run skip — inherited local-OCR-only test because Tesseract is intentionally absent from the ordinary integration runner
- cleaning fixture evidence — passed
- chunking fixture evidence — passed
- dense Qdrant fixture evidence — passed
- sparse BM25 fixture evidence — passed
- hybrid RRF fixture evidence — passed
- reranked retrieval-service fixture evidence — passed
- Phase 10 grounded-generation fixture evidence — passed
- package smoke — `rageval smoke: ok (development)`
- full cumulative suite — **153 passed, 1 skipped in 2.65s**
- Compose teardown — passed

Dedicated OCR:

- Tesseract **5.3.4** installed
- local OCR fixture — **1 passed in 0.60s**

Final PR-head run `34806206207` repeated the complete three-job gate on head `ec550e6cb1251f9dbb65894c3adc470fa2dd7456`.
Independent post-merge run `34806319174` repeated the complete three-job gate on merge commit `87c2c329a12aa4fc3d4a5eb775ed2df32c3ce111`.

No test, assertion, lint/type gate, prior cleaning/chunking/dense/sparse/hybrid/reranking evidence step, smoke check, full regression test, or OCR validation was removed or weakened.

## Machine-readable Phase 10 fixture evidence

Command:

```bash
python scripts/generation_fixture_report.py
```

Accepted-run fixture identity:

- source documents: **4**
- canonical chunks: **6**
- chunk strategy inherited from fixture pipeline: `fixed_512`
- generation provider: `deterministic-fake`
- generation model: `deterministic-grounded-generator-v1`
- retrieval-service configuration fingerprint: `1fb23ec813c4ef27b156ac654620effed71f0c6154f995f50128c8bccdfd6856`
- sparse index fingerprint: `1be008c07ac70d1b09aceb41aeed4965903016bb05e9bbe3fd1bc884ff2ea20e`
- generation configuration fingerprint: `6b2bba681505a024536b962965e3e754190fde07416b7689ae8f976be607b508`
- context configuration fingerprint: `3e21ad11a5cf2934c6babde30cce2247bec8a4f8d8c42fc8e5f50cf2467c0f42`

### Answerable fixture proof

Question text is the exact first canonical fixture chunk:

`Financial Report Fixture Example Corp reported revenue of $125 million in Q3 2026. Operating margin increased to 18.4 percent from 16.9 percent.`

Evidence:

- `insufficient_context`: `false`
- cited chunk IDs: `chk_0aa1f9408acc9a91748da01bf8ba93ee`
- assembled context IDs:
  1. `chk_0aa1f9408acc9a91748da01bf8ba93ee`
  2. `chk_7d020b519dc5dec344a7d1213b6414a7`
  3. `chk_2b552c53fff02bba707df0f7e2e51db6`
  4. `chk_faa095f91126fa6e1a6bf03c400a19c7`
  5. `chk_1546d99922b41acf731a9877e524839e`
- deterministic context token count: **129**
- repair count: **0**

The cited ID is therefore present in the exact supplied assembled context and remains traceable to the Phase 9 retrieval response.

### Unanswerable fixture proof

Question:

`What is the lunar population of Europa in 2125?`

Evidence:

- `insufficient_context`: `true`
- citations: `[]`
- refusal reason: `deterministic fixture marked the question unsupported`

This proves the completion-gate mechanics for explicit refusal without unsupported citation. It is not a production hallucination-rate or answer-quality benchmark.

## Failure and repair history

1. Initial PR run `34766881183`: runtime integration, inherited fixture chain, new generation fixture, full regression, and dedicated OCR all passed. Quality stopped at Ruff import-order/line-length/builtin-timeout style findings.
2. Those exact lint issues were fixed without changing assertions or runtime semantics. Run `34767130194` then passed Ruff; Ruff formatter identified five files needing canonical layout.
3. Ruff's exact formatting changes were applied. Run `34767280650` passed lint, formatting, integration/full regression, and OCR. Strict mypy then found one local variable-name collision in `generation/providers.py` where a retry error string and parsed provider message object reused the same name.
4. The local variable was renamed rather than suppressing typing. Run `34767396626` passed all three jobs and became the accepted implementation run.
5. Canonical Phase 10 plan/report/status documentation was added without changing runtime behavior. Final PR-head run `34806206207` passed all three jobs; PR #10 was then marked ready and merged with exact-head protection.
6. Merge commit `87c2c329a12aa4fc3d4a5eb775ed2df32c3ce111` triggered independent `main` run `34806319174`, which passed all three jobs and closed the behavioral acceptance loop.

## Provider validation

Executed:

- deterministic fake generation success and explicit refusal;
- deterministic malformed output and citation-repair mechanics;
- deterministic timeout/provider-error behavior;
- OpenAI hosted-adapter request/response parsing using mocked HTTP;
- OpenAI 429 retry then success using mocked HTTP;
- OpenAI timeout exhaustion using mocked HTTP.

Not executed:

- live OpenAI generation — **not run because no credential-enabled live validation was available**;
- Anthropic generation — **not implemented; OpenAI satisfies the required hosted reference path**.

The repository therefore has a complete credential-free deterministic generation mechanics path plus a tested hosted OpenAI adapter, but no live hosted-model quality evidence is claimed.

## Known limitations

- Acceptance corpus is **4 documents / 6 chunks**, not the target roughly 12,000-document corpus.
- Deterministic fake generation validates orchestration/structure/citation mechanics, not model answer quality.
- The local hash dense provider and deterministic reranker remain mechanics-only components in this fixture pipeline.
- Live OpenAI generation was not exercised against the hosted service.
- Context token counting is deterministic mechanics accounting, not exact hosted-model tokenizer accounting.
- Citation validation currently proves cited canonical IDs exist in supplied context; semantic claim entailment is not yet scored.
- Prompt-injection testing proves the context/system separation and application-side validation path, not universal robustness against all hosted-model attacks.
- The conservative Self-RAG router is not supported by representative quality/cost evaluation and is not the default.
- The no-retrieval route intentionally refuses instead of emitting an answer under the grounded-answer guarantee.
- No target-corpus generation, faithfulness, hallucination-rate, answer-relevancy, or cost benchmark is claimed.
- GitHub Actions continues to emit a non-failing Node action deprecation warning from the current checkout/setup-python action versions.

## Reproducible commands

From a clean checkout with Python 3.11 and Docker available:

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src
pytest -q tests/unit
docker compose config
docker compose up -d qdrant redis
pytest -q tests/integration
python scripts/cleaning_fixture_report.py
python scripts/chunking_fixture_report.py
python scripts/dense_fixture_report.py
python scripts/sparse_fixture_report.py
python scripts/hybrid_fixture_report.py
python scripts/retrieval_service_fixture_report.py
python scripts/generation_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated installed-OCR validation remains the separate CI job:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

## Phase 11 handoff

Phase 11 should consume the stable Phase 10 `GroundedAnswer`/`GroundedGenerationResponse` and existing retrieval diagnostics to define the evaluation dataset, metric contracts, and judge interfaces without hard-coding unverified reference-document scores. Retrieval-context metrics should operate on canonical chunk identities/provenance; generation metrics should distinguish citation traceability from semantic faithfulness/entailment; insufficient-context/refusal cases must be represented explicitly rather than forced into ordinary answer scoring.

Any LLM-as-judge path should remain provider-abstracted, deterministic-testable, structured, auditable, and separate from hidden chain-of-thought. The target roughly 200-question evaluation set remains a project target and must not be fabricated if the actual data is unavailable.
