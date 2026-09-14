# Phase 11 Report — Evaluation Dataset, Metrics & Judge Contracts

## Status

**Complete.** Phase 11 is merged to `main` and independently revalidated after merge.

Final validated PR head: `e3e2bd1388961fe8c5ba83c57a7be6f8066f60a8`.
Final PR-head GitHub Actions run: `34819678161` — quality, real-service integration/evidence/full regression, and dedicated installed-Tesseract OCR all passed.
Merge commit: `5cdfcaa409545cc448a8a3d99ecfd066c0239a8a`.
Independent merge-triggered `main` run: `34819832613` — all three jobs passed again.

Accepted implementation head: `d98b06cbfd676bf150c59ad8c78f1777672751b1`.
Accepted implementation run: `34819276865` — all three jobs passed.

The target roughly 200-question held-out evaluation set was not supplied. It was not fabricated. Phase 11 acceptance uses a clearly labeled three-record reviewed synthetic fixture for deterministic mechanics and arithmetic only.

No live LLM judge or real RAGAS execution is claimed. Deterministic/local acceptance is complete; the optional RAGAS boundary is tested with an injected scorer only.

## Mission delivered

Phase 11 establishes the measurement contracts that consume the stable retrieval and grounded-generation outputs from Phases 6–10. It finalizes held-out evaluation-example governance, validates leakage-sensitive dataset metadata, computes reproducible per-example and aggregate metrics, defines structured and auditable judge contracts, and fingerprints datasets/configurations/runs so later ablations can be compared without copying headline values from documentation.

All reported metric values are produced from actual evaluation records. No benchmark score is hard-coded into the engine or report path.

## Architecture decisions

### Stable evaluation contracts

`EvaluationExample` is extended compatibly rather than replaced. New Phase 11 fields have defaults so earlier callers remain valid while reviewed datasets can carry:

- schema version;
- question and reference answer;
- domain;
- supporting document IDs and canonical chunk IDs when known;
- tags;
- table-parsing flag;
- held-out split marker;
- provenance;
- reviewer status and optional reviewer identity.

`EvaluationResult` is also extended with defaulted audit/version/fingerprint fields rather than introducing a parallel result type.

The Phase 2 `EvaluationDatasetRecord` remains the wrapper that binds an example to held-out source documents and a corpus fingerprint.

### Dataset loading, review tooling, and leakage validation

Phase 11 provides strict JSONL loading/writing, duplicate-example validation, deterministic ordering/fingerprinting, and review CSV export. When a corpus manifest is available, dataset validation requires the record corpus fingerprint to match the manifest and rejects evaluation records that reference development-split documents.

This extends rather than replaces the Phase 2 corpus-level checksum/document-identity split-leakage checks. The current fixture is synthetic and small; the real target dataset can use the same contracts when supplied.

### Context metrics

Context precision and context recall operate on sets of canonical chunk IDs. Duplicate retrieved chunk IDs cannot inflate a denominator.

Current deterministic definitions are:

- context precision = `|retrieved ∩ supporting| / |retrieved|`;
- context recall = `|retrieved ∩ supporting| / |supporting|`.

An empty retrieved set scores precision 1 only when no supporting chunks are required; otherwise 0. No required supporting chunks are treated as recall 1. These edge conventions are explicit and tested.

### Faithfulness and answer relevancy

Faithfulness is claim-level. Explicit citation claims are preferred; otherwise a non-refusal answer is deterministically split into claims. Each claim is sent through the structured judge boundary against only the supplied context. Per-example faithfulness is the mean claim-support score.

An explicit insufficient-context refusal with no claims is treated as faithful for this metric because it makes no unsupported factual claim. An empty non-refusal answer scores zero.

Answer relevancy uses the same structured judge boundary but evaluates whether the produced answer addresses the question/reference. The deterministic acceptance judge is lexical mechanics only; it is not represented as a semantic-quality benchmark.

### Hallucination definition and arithmetic

The project definition is implemented exactly:

`hallucinated = faithfulness < 0.8`

The threshold is strict: faithfulness exactly `0.8` is not flagged.

Aggregate hallucination output persists:

- `flagged_count`;
- `total_count`;
- `rate`;
- threshold.

`HallucinationSummary` validates that `rate == flagged_count / total_count` (with the defined empty-set convention) and rejects inconsistent count/rate combinations. No percentage is accepted independently from its numerator and denominator.

### Structured judge contracts

`JudgeProvider` isolates semantic judging from the evaluation engine. Requests carry metric, question, candidate text, reference answer, supplied context, prompt version, and rubric version. Responses carry:

- normalized score and verdict;
- concise auditable rationale;
- evidence chunk IDs;
- provider/model identity;
- prompt/rubric version.

Judge schemas are strict and do not include hidden chain-of-thought. Tests reject unexpected hidden-reasoning fields.

`DeterministicRuleJudge` provides the credential-free acceptance baseline. `ScriptedJudge` provides exact fake outputs for arithmetic/edge tests.

### Optional RAGAS boundary

`RagasMetricAdapter` is a narrow stable wrapper around an injected asynchronous scorer and records the supplied RAGAS version. The core package does not add RAGAS as a mandatory dependency in this phase. Unit tests validate adapter mechanics and output range using an injected scorer.

No installed RAGAS package run, RAGAS metric result, or hosted-model result is claimed from Phase 11 acceptance.

### Reproducible evaluation engine

`EvaluationEngine` validates example/observation identity, evaluates each example, emits per-example `EvaluationResult` records, computes aggregate means from those records, calculates hallucination counts/rate from actual faithfulness results, and returns deterministic dataset/config/run fingerprints.

The run fingerprint is stable when observation input ordering changes, which allows Phase 12 to compare configuration-specific results reliably.

## Files changed

Production:

- `src/rageval/models/contracts.py`
- `src/rageval/evaluation/__init__.py`
- `src/rageval/evaluation/dataset.py`
- `src/rageval/evaluation/models.py`
- `src/rageval/evaluation/judges.py`
- `src/rageval/evaluation/metrics.py`
- `src/rageval/evaluation/engine.py`

Tests, fixtures, evidence, and CI:

- `tests/fixtures/evaluation/phase11_records.jsonl`
- `tests/unit/test_evaluation_dataset_phase11.py`
- `tests/unit/test_evaluation_metrics.py`
- `tests/unit/test_evaluation_judges.py`
- `tests/unit/test_evaluation_engine.py`
- `tests/integration/test_evaluation_engine.py`
- `scripts/evaluation_fixture_report.py`
- `.github/workflows/ci.yml`
- `Makefile`

Documentation:

- `docs/plans/phase-11-evaluation-dataset-metrics-judge-contracts.md`
- this report

The feature branch also removed an accidental temporary `docs/plans/phase-11-noop.txt` file from its base history.

## Required behavior tests

Coverage verifies:

- Phase 11 evaluation-example fields round-trip through strict models;
- evaluation JSONL fingerprinting is order-independent;
- duplicate example IDs are rejected;
- mismatched corpus fingerprints are rejected when a manifest is supplied;
- evaluation records cannot reference development-split documents;
- review CSV output contains reviewer/support metadata;
- context precision deduplicates retrieved IDs;
- empty-context/no-required-support edge conventions;
- claim-level partial-support faithfulness arithmetic;
- refusal/no-claim behavior;
- empty non-refusal answer behavior;
- answer relevancy uses structured judge output;
- hallucination threshold is strictly `< 0.8`;
- impossible/inconsistent hallucination count/rate combinations fail validation;
- judge output parsing is strict and hidden-reasoning extras are rejected;
- optional RAGAS adapter range validation;
- evaluation run fingerprint stability under observation reordering;
- tiny deterministic integration evaluation returns reproducible per-example records and aggregate arithmetic.

## Accepted verification evidence

Accepted implementation head: `d98b06cbfd676bf150c59ad8c78f1777672751b1`

Accepted implementation run: `34819276865`

Quality:

- Python **3.11.16**
- Ruff lint — passed
- Ruff formatter — passed; **149 files already formatted**
- strict mypy — **no issues in 71 source files**
- unit suite — **147 passed in 1.66s**

Integration:

- Docker Compose configuration — passed
- local Qdrant/Redis startup/readiness — passed
- ordinary integration suite — **29 passed, 1 skipped in 2.79s**
- sole ordinary-run skip — inherited local-OCR-only test because Tesseract is intentionally absent from the ordinary integration runner
- cleaning fixture evidence — passed
- chunking fixture evidence — passed
- dense Qdrant fixture evidence — passed
- sparse BM25 fixture evidence — passed
- hybrid RRF fixture evidence — passed
- reranked retrieval-service fixture evidence — passed
- grounded-generation fixture evidence — passed
- Phase 11 evaluation-metrics fixture evidence — passed
- package smoke — `rageval smoke: ok (development)`
- full cumulative suite — **176 passed, 1 skipped in 3.09s**
- Compose teardown — passed

Dedicated OCR:

- Tesseract **5.3.4** installed
- local OCR fixture — **1 passed in 0.82s**

Final PR-head run `34819678161` repeated the complete three-job gate on head `e3e2bd1388961fe8c5ba83c57a7be6f8066f60a8`. Independent post-merge `main` run `34819832613` repeated the same gate on merge commit `5cdfcaa409545cc448a8a3d99ecfd066c0239a8a`.

No test, assertion, lint/type gate, prior cleaning/chunking/dense/sparse/hybrid/reranking/generation evidence step, smoke check, full regression test, or OCR validation was removed or weakened.

## Machine-readable Phase 11 fixture evidence

Command:

```bash
python scripts/evaluation_fixture_report.py
```

Accepted-run fixture identity:

- fixture records: **3**
- target dataset supplied: **false**
- evidence label: `deterministic-fixture-mechanics-only`
- dataset fingerprint: `5dad39bffb7acd7ac15414a10b9a654461a4ba0ff4642f7c66281733fd9c4cc0`
- evaluation configuration fingerprint: `89fbf59dba96baec81e6437d22b50451fcb697327adc4249f854173dbf698d38`
- run fingerprint: `487bfc426c609b97c65f660626d75b9672281b89deee94be361a98017c69e858`
- judge provider: `deterministic-rule`
- judge model: `lexical-overlap-v1`
- judge prompt version: `phase11-judge-prompt-v1`
- judge rubric version: `phase11-rubric-v1`

Actual aggregate output from the accepted run:

- context precision: **0.8333333333333334**
- context recall: **0.8333333333333334**
- faithfulness: **0.8333333333333334**
- answer relevancy: **0.711965811965812**
- hallucination threshold: **0.8**
- flagged responses: **1**
- total responses: **3**
- hallucination rate: **0.3333333333333333**

The legal synthetic example intentionally contains one unsupported claim, producing faithfulness **0.5** and one flagged response. The financial and research examples are not flagged. The rate is computed from the records as `1 / 3`; it is not a documentation constant.

These numbers are deliberately not presented as production or target-corpus quality results. They characterize this three-record deterministic mechanics fixture only.

## Failure and repair history

1. Initial PR run `34807880289`: integration, all inherited evidence, the new Phase 11 evaluation report, full regression, and dedicated OCR passed. Quality passed Ruff lint but Ruff formatter identified five files needing canonical layout before mypy/unit ran.
2. Exact formatter output was applied. Run `34808104469` then exposed one Ruff E501 line-length issue in the formatted claim generator; runtime integration/OCR remained green.
3. The claim expression was restructured. Run `34808160656` passed lint but formatter still wanted to collapse the generator, which would recreate E501. This was treated as a lint/formatter interaction rather than suppressed.
4. Claim normalization and empty filtering were split into two short generators, preserving semantics while satisfying both canonical gates. Run `34819276865` then passed lint, formatter, strict mypy, unit, full integration/evidence/regression, and dedicated OCR together.

No lint rule, type-checking strictness, test assertion, or CI evidence step was weakened during repair.

## Provider and external-metric validation

Executed:

- deterministic lexical rule judge;
- scripted fake judge;
- strict structured judge request/response parsing;
- prompt/rubric/provider/model version propagation;
- optional RAGAS adapter mechanics with an injected fake scorer and score-range validation.

Not executed:

- live LLM judge — **not run because no credential-enabled live validation was available**;
- actual RAGAS package-backed evaluation — **not installed/executed in the acceptance path**;
- target roughly 200-question evaluation set — **not supplied and therefore not fabricated**.

## Known limitations

- Acceptance data is only **3 reviewed synthetic fixture examples**, not the target roughly 200-question held-out set.
- The deterministic lexical judge validates orchestration, schema, arithmetic, and audit mechanics; it is not a substitute for semantic judge quality.
- RAGAS is represented by a stable adapter contract only; no RAGAS-backed score is claimed.
- No live LLM judge was exercised.
- Context precision/recall require supporting canonical chunk labels when those metrics are expected to be meaningful; examples without complete support labels need explicit treatment in later dataset curation.
- The fixture hallucination rate `1/3` is not a production hallucination-rate estimate.
- Citation traceability from Phase 10 and semantic claim entailment are intentionally distinct concerns.
- No target-corpus, per-domain, hosted-provider, cost, or production-quality benchmark is claimed.
- The real corpus and target held-out set remain prerequisites for representative evaluation.

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
python scripts/evaluation_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated installed-OCR validation remains the separate CI job:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

## Phase 12 handoff

Phase 12 should consume the stable Phase 11 dataset/metric/judge/run contracts to implement the evaluation runner, controlled retrieval/generation ablations, persisted run artifacts, per-domain slicing, and failure analysis. Configuration-specific results must retain the Phase 11 dataset/config/run fingerprints so comparisons cannot silently mix datasets or metric versions.

The real target evaluation set remains absent. Phase 12 must continue using deterministic fixtures for acceptance and must not manufacture representative benchmark claims until reviewed evaluation data and any required provider credentials are actually available.
