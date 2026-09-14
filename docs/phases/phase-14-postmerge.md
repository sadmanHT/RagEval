# Phase 14 Post-Merge Closure

Phase 14 — Observability, Docker/Compose, CI/CD, Security & Operational Hardening — is merged and independently revalidated on `main`.

## Merge identity

- Pull request: **#14**
- Final validated PR head: `5eae2668b1543c7fc845fd6470d08f3e35b6705d`
- Final report-bearing PR CI: **GitHub Actions run `34834619090`**
- Merge commit: `b73951c107fa02c9c6ccc366221b9aafb77d205d`
- Independent merge-triggered `main` CI: **GitHub Actions run `34834859774`**

The PR was moved out of draft only after all five exact-head jobs passed, and the merge used the validated expected head SHA.

## Independent `main` validation

Run `34834859774` passed all five jobs on the merge commit:

- quality — lint, format, strict mypy, and unit tests;
- integration — all inherited fixture evidence, Phase 14 PR-fast evaluation gate, serving evidence, smoke, and full host regression;
- container — clean Compose validation/build, non-root assertion, clean-volume operational stack, authenticated observability smoke, the full repository suite in the Tesseract-enabled test image, and live Qdrant outage/readiness/metrics drill;
- security — Python dependency audit and secret scan;
- local-ocr — independently installed Tesseract fixture.

Accepted implementation counts remain:

- **181 unit tests passed**;
- **31 ordinary integration tests passed, 1 skipped** because ordinary integration intentionally does not install Tesseract;
- **212 host cumulative tests passed, 1 skipped** for the same OCR reason;
- **213 cumulative tests passed inside the Tesseract-enabled container**;
- strict mypy passed on **90 source files**;
- dedicated installed-Tesseract OCR passed.

The operational stack also retained the accepted evidence from the final PR head: runtime UID **10001**, authenticated cited query, successful evaluation-job lifecycle, metrics exposure, Prometheus scrape health, Grafana health, and Qdrant outage degradation with `rageval_dependency_ready{component="qdrant"} 0.0`.

## Evidence boundary

The Phase 14 operational evidence is deterministic fixture/mechanics evidence. The representative roughly 12,000-document corpus and roughly 200-question reviewed evaluation set remain absent. No live OpenAI, Cohere, Langfuse, or W&B result, production load/SLO/cost benchmark, statistically significant drift result, or target-corpus quality result is claimed.

Known limits remain documented in `docs/phases/phase-14-report.md` and `docs/operations.md`: the rate limiter is per process, evaluation-job state is in-process/non-durable, `/metrics` needs deployment-layer network restriction in production, Python dependencies are bounded rather than fully hash-locked, and Qdrant recovery is reindex-first rather than an environment-specific snapshot-restore claim.

## Closure head

This post-merge record is part of the final documentation closure state. The exact final `main` head containing the README, implementation-state, and this file must itself pass the same five-job CI matrix before Phase 14 is considered completely closed.