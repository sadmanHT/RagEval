# Phase 11 — Evaluation Dataset, Metric Implementations & Judge Contracts

Canonical repository copy of the Phase 11 execution contract supplied for this implementation.

## Mission

Build the measurement system that is the core of RAG-Eval. Metrics must be explicit, reproducible, auditable, and arithmetically correct.

## Required scope

- Finalize the evaluation-example schema with reference answer, supporting document/chunk references, domain, tags, table-parsing flag, held-out split, provenance, and reviewer status.
- Load and validate a supplied held-out set; when the target ~200-question set is unavailable, keep acceptance on a small fixture set and do not fabricate target data.
- Reuse corpus fingerprint/checksum leakage guards.
- Implement context precision, context recall, answer faithfulness, answer relevancy, and response-level hallucination classification/rate.
- Define hallucination as `faithfulness < 0.8`; aggregate as actual flagged count divided by actual evaluated count, persisting both numerator and denominator.
- Keep semantic/judge providers behind stable adapters. Structured judge outputs must record provider/model/prompt/rubric versions and concise auditable rationale/evidence; do not persist hidden chain-of-thought.
- Provide deterministic rule/fake judges for acceptance tests.
- Add arithmetic, edge-case, leakage, structured-output, version/fingerprint, and tiny end-to-end evaluation tests.
- Retain every Phase 1–10 quality/integration/evidence/OCR gate.

## Completion gate

Given a small known fixture set, the evaluation engine must return reproducible per-example metric records and correct aggregate math. No headline metric may come from a constant or documentation value.
