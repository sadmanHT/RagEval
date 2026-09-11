# Architecture Decisions

## ADR-001 — Provider boundaries are protocols

External embeddings, rerankers, LLMs, tracing, and experiment tracking are accessed through typed protocols. Deterministic fakes implement the same protocols for tests. Hosted SDK objects must not leak across these boundaries.

## ADR-002 — Weights & Biases is the primary experiment-tracking target

The reference specification mentions both MLflow and Weights & Biases. The first implementation targets a W&B adapter behind `ExperimentTracker`; a future MLflow adapter can implement the same contract. Local evaluation artifacts remain mandatory even when cloud tracking is disabled.

## ADR-003 — Deterministic IDs are content/config-derived

Document/chunk identifiers and configuration fingerprints use SHA-256 over explicit canonical inputs. Random UUIDs are not used for reproducible corpus identities.

## ADR-004 — Test tiers are explicit

Deterministic unit/integration tests form the acceptance baseline. Live-provider tests are additional evidence and are never allowed to replace deterministic acceptance.

## ADR-005 — Local/offline claims require end-to-end local adapters

The project may only claim complete credential-free operation after embeddings, reranking, and generation all have tested local adapters. Phase 1 therefore uses fakes for deterministic tests but makes no production offline claim.
