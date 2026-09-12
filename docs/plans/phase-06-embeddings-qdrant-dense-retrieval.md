# Phase 6 — Embeddings, Qdrant Indexing & Dense Retrieval

Source contract: uploaded Phase 6 implementation plan.

## Mission
Implement reproducible dense indexing and search with Qdrant while keeping embedding providers replaceable and testable.

## Required scope
- embedding-provider abstraction with a deterministic fake, OpenAI `text-embedding-3-large` reference adapter, and a truthful local/offline path where supported;
- Qdrant collection management with vector dimension/distance validation, collection versioning, and payload indexes for domain/date/document metadata;
- idempotent batch upsert, delete/reindex by document, and index consistency checks;
- reconstructable chunk text/provenance/config metadata in Qdrant payloads;
- dense search with top-k, domain/date/document filters, stable result schema, scores, latency measurement, and configurable HNSW/search parameters;
- explicit dimension-mismatch/stale-schema errors with migration guidance;
- deterministic provider tests, real-local-Qdrant integration, relevance sanity, idempotent reingestion, filters, failure paths, and parser/cleaner/chunker -> embedding -> Qdrant -> retrieval provenance end to end;
- full cumulative regression.

## Truthfulness rules
Reference corpus sizes/provider models are targets, not run evidence. Do not fabricate provider results. Hosted-provider tests are additive; deterministic/local acceptance is mandatory. No unsupported embedding fine-tuning claim is permitted.
