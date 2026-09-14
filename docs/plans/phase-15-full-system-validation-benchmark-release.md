# Phase 15 — Full-System Validation, Roadmap Closure, Benchmarking & Release

This phase is the adversarial final acceptance and release phase for RAG-Eval. It preserves the project’s measurement-first philosophy: no architecture change is an improvement without evaluation evidence, deterministic/local acceptance comes before live-provider validation, and absent target data or credentials must be recorded as blocked rather than fabricated.

## Mission

Prove that the implemented system works together from ingestion through serving, observability, and evaluation. Run financial, legal, and research scenarios; table-aware retrieval; vocabulary mismatch/query expansion; multi-hop recovery; insufficient-context refusal; retry/timeout behavior; index rebuild; cache invalidation; evaluation resume; API concurrency; and dependency outage/recovery.

## Release evidence

The release gate must execute static checks, unit/integration/regression suites, clean container/Compose validation, local end-to-end validation, security checks, resilience checks, measured latency/load evidence, the full available reviewed evaluation set with raw records plus aggregates, optional live-provider smoke only when credentials are available, and clean-checkout reproducibility.

The target roughly 12,000-document corpus and roughly 200-question reviewed evaluation set remain project targets. They must never be fabricated when absent. Benchmark numbers must be generated from actual run records with environment and sample size. Fixture-only ablations may reconcile mechanics and contradictions but cannot select a production strategy without representative evidence.

## Closure conditions

A release may be called complete only when all deterministic tiers and the containerized end-to-end flow are green; no high-severity security or citation/data-loss defect is open; benchmark/evaluation artifacts come from actual records; documentation matches implementation; blocked external validation is explicit; and the final phase report records exact commands, versions, counts, environment, metrics, limitations, and handoff state.
