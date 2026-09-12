# Phase 6 Validation Worklog

Phase 6 implementation is validated through GitHub Actions before completion claims.

Deterministic acceptance scope:
- dense embedding provider contract plus local deterministic dimensions;
- mocked OpenAI `text-embedding-3-large` request/ordering/dimension/error behavior without credentials;
- Qdrant collection creation/schema validation/payload indexes;
- deterministic UUID point identity and idempotent upsert;
- domain/date/document/chunking-config filters;
- replace/delete/consistency operations;
- stale-vector-schema and unavailable-Qdrant failures;
- parser -> cleaner -> chunker -> local embedding -> real Qdrant -> canonical retrieval provenance;
- machine-readable dense fixture evidence plus all prior quality/integration/OCR/regression gates.

Live OpenAI validation is additive and must be recorded as blocked unless credentials are actually available to the run.
