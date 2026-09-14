# Phase 12 Report — Evaluation Runner, Ablations & Failure Analysis

## Status

**Implementation acceptance complete; merge/post-merge closure pending.**

Accepted implementation head: `7d91009058ccdc680de7f59ee6f53c9f01461d5b`.
Accepted implementation GitHub Actions run: `34825099209` — quality, the complete inherited integration/evidence/full-regression chain, and dedicated installed-Tesseract OCR all passed.

The target roughly 200-question held-out evaluation set and representative roughly 12,000-document corpus are still not present. They were not fabricated. Phase 12 acceptance therefore uses the existing three-record reviewed synthetic evaluation fixture plus deterministic/local providers to validate runner, ablation, reporting, regression, and failure-analysis mechanics only.

No preferred chunking/retrieval configuration, target-corpus quality improvement, hosted-provider quality result, production latency result, or production hallucination rate is claimed from the Phase 12 fixture.

## Mission delivered

Phase 12 turns the Phase 11 metric and judge contracts into a repeatable comparative-evaluation pipeline. It can run configuration matrices, resume from per-example checkpoints, retry bounded failures, persist auditable run artifacts, aggregate metrics overall and by domain, classify observable failure modes, compare candidate metrics against explicit regression policies, log experiments through the existing tracker abstraction, and emit JSON/Markdown/HTML reports from the same immutable result model.

The implementation preserves the repository's evaluation-first rule: every reported metric is recomputed from per-example evaluation records, and fixture-only differences are explicitly labeled as non-representative.

## Architecture decisions

### One generic observation boundary, not a parallel RAG stack

`ObservationProvider` is the Phase 12 seam between configuration-specific system execution and evaluation. It accepts an `EvaluationDatasetRecord` plus an `AblationConfiguration` and returns the existing Phase 11 `EvaluationObservation` contract.

This keeps the runner independent of hosted providers and avoids embedding a second retrieval/generation architecture inside evaluation. Existing Phase 9/10 production services remain the canonical retrieval/generation stack. Representative production ablations can be wired through this boundary when the real corpus/index, reviewed evaluation set, and provider configuration are available.

The deterministic fixture provider intentionally varies observations by configuration to exercise the comparative mechanics. It is not represented as a learned or production observation provider.

### Bounded asynchronous execution and resume

`AsyncEvaluationRunner` executes examples with a configurable semaphore, bounded attempts, and exponential retry backoff. Each completed observation is stored as an atomic JSON checkpoint scoped by:

- configuration ID;
- example ID;
- dataset fingerprint;
- configuration fingerprint.

Resume rejects stale checkpoints when dataset/configuration fingerprints differ and verifies that the stored example payload still matches the held-out dataset record. A failed run can therefore resume completed examples without silently mixing incompatible evidence.

### Explicit configuration matrices

`AblationConfiguration` and `EvaluationMatrix` cover the Phase 12 comparison dimensions:

- dense-only;
- dense + BM25/RRF hybrid;
- hybrid + rerank;
- fixed 256/512/1024 chunking;
- semantic chunking;
- table-aware chunking;
- query expansion on/off;
- multi-hop on/off.

Duplicate configuration IDs are rejected. Each configuration and each complete matrix has a deterministic fingerprint, and each resulting configuration run receives a deterministic run ID incorporating dataset/configuration/evaluation/corpus/git identity.

### Run metadata and reproducibility

Configuration-run metadata records:

- git commit;
- evaluation dataset fingerprint;
- corpus/index fingerprint;
- configuration fingerprint;
- provider/model versions supplied by the configuration;
- prompt versions;
- chunking strategy/config;
- retrieval parameters;
- timestamp;
- machine/Python/platform summary;
- observation-provider identity;
- judge provider/model;
- metric version.

Unknown git state is represented explicitly as `unknown`; it is not invented.

### Aggregation with sample counts

Metric slices are recomputed from persisted per-example evaluation records. The runner emits overall and per-domain (`financial`, `legal`, `research`) means together with sample counts. The report surface includes those counts so tiny fixture differences cannot be presented without their denominator.

Phase 12 intentionally does not choose a globally preferred configuration from the three-record fixture.

### Failure taxonomy

Failure analysis can classify the required observable categories:

- table fragmentation;
- vocabulary mismatch;
- long-range reference;
- retrieval miss;
- reranker error;
- citation failure;
- unsupported generated claim;
- unknown.

Classification uses explicit dataset tags/metadata, retrieval/evaluation signals, citation membership, and hallucination state. It does not fabricate a cause when evidence is insufficient; unexplained degraded records fall back to `unknown`.

### Regression policies distinguish PR gates from nightly alerts

The regression comparator operates over metric/domain slices and explicit thresholds. It detects improvement, degradation, missing metrics, and sample-size mismatch.

`PR_FAST` violations are blocking gate failures. `NIGHTLY_FULL` violations raise alerts without being misrepresented as a pre-merge blocker. This resolves the documentation inconsistency where a post-merge nightly job had previously been described as capable of blocking a PR.

### Experiment tracking and local reports

Phase 12 reuses the Phase 1 `ExperimentTracker` abstraction rather than introducing a second experiment-tracking contract. The accepted local path includes:

- existing deterministic fake tracker for tests;
- credential-free JSONL tracker;
- optional lazy W&B adapter boundary;
- mandatory JSON, Markdown, and HTML comparative reports.

Cloud tracking is supplementary. Local evidence remains available when W&B credentials/dependencies are absent.

## Files changed

Production:

- `src/rageval/evaluation/__init__.py`
- `src/rageval/evaluation/failures.py`
- `src/rageval/evaluation/regression.py`
- `src/rageval/evaluation/reporting.py`
- `src/rageval/evaluation/run_models.py`
- `src/rageval/evaluation/runner.py`
- `src/rageval/evaluation/tracking.py`

Tests and evidence:

- `tests/unit/test_evaluation_failures_phase12.py`
- `tests/unit/test_evaluation_regression_phase12.py`
- `tests/unit/test_evaluation_reporting_tracking_phase12.py`
- `tests/unit/test_evaluation_runner_phase12.py`
- `tests/integration/test_evaluation_ablation_phase12.py`
- `scripts/evaluation_ablation_fixture_report.py`
- `.github/workflows/ci.yml`
- `Makefile`

Documentation:

- `docs/plans/phase-12-evaluation-runner-ablation-failure-analysis.md`
- this report

## Required behavior tests

Phase 12 adds **14 unit tests** and **1 integration test** covering:

- resume after an injected example failure without recomputing successful checkpoints;
- bounded concurrency and deterministic evaluation ordering;
- transient example retry;
- duplicate configuration-ID rejection;
- regression improvement;
- blocking PR-fast degradation;
- non-blocking nightly degradation alert;
- missing-metric regression detection;
- sample-size mismatch detection;
- complete named failure-taxonomy signals;
- unknown fallback when degraded metrics have no classified cause;
- perfect-record no-failure behavior;
- JSON/Markdown/HTML report generation;
- local JSON tracker plus the existing fake tracker;
- five-configuration fixture ablation with distinct run/config fingerprints and recomputation of summaries from per-example records.

No inherited test was replaced to obtain these counts.

## Accepted verification evidence

Accepted implementation head: `7d91009058ccdc680de7f59ee6f53c9f01461d5b`

Accepted implementation run: `34825099209`

Quality:

- Ruff lint — passed
- Ruff formatter — passed
- strict mypy — passed
- unit suite — **161 passed**

Integration:

- Docker Compose configuration — passed
- local Qdrant/Redis startup/readiness — passed
- ordinary integration suite — **30 passed, 1 skipped**
- sole ordinary-run skip — inherited local-OCR-only test because Tesseract is intentionally installed only in the dedicated OCR job
- cleaning fixture evidence — passed
- chunking fixture evidence — passed
- dense Qdrant fixture evidence — passed
- sparse BM25 fixture evidence — passed
- hybrid RRF fixture evidence — passed
- reranked retrieval-service fixture evidence — passed
- grounded-generation fixture evidence — passed
- Phase 11 evaluation-metrics fixture evidence — passed
- Phase 12 comparative-evaluation ablation fixture evidence — passed
- package smoke — passed
- full cumulative suite — **191 passed, 1 skipped**
- Compose teardown — passed

Dedicated OCR:

- Tesseract installation — passed
- local OCR fixture — passed

No lint rule, formatter gate, type-checking strictness, test assertion, previous evidence step, full regression check, or OCR validation was removed or weakened.

## Machine-readable Phase 12 fixture evidence

Command:

```bash
python scripts/evaluation_ablation_fixture_report.py
```

The script executes **5 distinct configurations** across the same **3 reviewed synthetic records**:

- dense + fixed-256;
- hybrid RRF + fixed-512;
- hybrid rerank + fixed-1024;
- hybrid rerank + semantic + query expansion;
- hybrid rerank + table-aware + query expansion + multi-hop.

It verifies that:

- the target dataset is explicitly marked as not supplied;
- all five configuration IDs produce distinct run IDs and configuration fingerprints;
- every required chunking label is represented;
- each overall metric slice reports `N = 3`;
- all summary slices equal recomputation from the underlying per-example records;
- one tracker event is emitted per configuration;
- JSON, Markdown, and HTML reports are all produced;
- the report evidence label is `deterministic-fixture-ablation-mechanics-only`.

The fixture deliberately injects configuration-dependent retrieval misses, distractors, and an unsupported claim so the comparative/failure-analysis machinery has non-identical records to process. Those differences are test fixtures, not evidence that one strategy is better on the target domains.

## Failure and repair history

1. The first Phase 12 CI candidate demonstrated that the runtime path already worked: integration, inherited evidence, the new comparative-evaluation fixture, full regression, and dedicated OCR passed. Quality stopped at Ruff formatter findings before mypy/unit.
2. Formatter-safe source changes were applied in `failures.py` and `regression.py` without changing semantics or weakening lint/tests.
3. The remaining formatter finding in `reporting.py` was repaired by using Ruff's canonical short f-string layout for the dataset/matrix fingerprint HTML lines.
4. Exact head `7d91009058ccdc680de7f59ee6f53c9f01461d5b` then passed all three jobs together in run `34825099209`, including lint, format, strict mypy, unit, integration/evidence/full regression, and installed OCR.

## Provider and representative-run validation

Executed:

- deterministic Phase 12 observation provider;
- deterministic Phase 11 rule judge through the real evaluation engine;
- local/fake experiment tracking;
- local JSON/Markdown/HTML reporting;
- real local Qdrant/Redis and every inherited retrieval/generation evidence step;
- installed-Tesseract OCR path.

Not executed/claimed:

- representative roughly 12,000-document corpus ablation — corpus not supplied;
- target roughly 200-question held-out evaluation run — dataset not supplied;
- live W&B run — not required for credential-free acceptance and not claimed;
- live hosted embedding/reranking/generation/judge provider benchmark — not claimed;
- production observation-provider benchmark over the deployed RAG stack — blocked on representative corpus/index/dataset/provider configuration;
- statistically meaningful confidence intervals — acceptance reports sample counts; representative data is required before inferential claims are useful.

## Known limitations

- The comparative fixture contains only **3 synthetic reviewed records** and cannot resolve the original documentation's real chunking-quality conflict by itself.
- Configuration-dependent fixture outcomes are intentionally scripted mechanics evidence, not semantic retrieval or generation quality evidence.
- The generic `ObservationProvider` boundary is ready for the real RAG stack, but Phase 12 does not claim a representative production ablation without the real corpus/index/evaluation dataset.
- No target-corpus per-domain winner, query-expansion benefit, multi-hop benefit, reranker benefit, or preferred chunk size is selected.
- W&B remains optional; no live W&B result is required or claimed.
- Sample counts are emitted, but confidence intervals/statistical tests should be added or enabled only when the representative evaluation set is available and large enough to support them.
- Existing hosted-provider limitations from Phases 6–11 remain unchanged.

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
python scripts/evaluation_ablation_fixture_report.py
python -m rageval.smoke
pytest -q
docker compose down -v
```

Dedicated installed-OCR validation remains separate:

```bash
pytest -q -m local_ocr tests/integration/test_local_ocr.py
```

## Closure sequence

Before Phase 12 is called fully closed, this report commit must pass the complete PR-head gate, PR #12 must be merged, and the merge commit must independently pass the same three-job CI gate on `main`. Final merge/main identifiers will be recorded after those checks succeed.
