# Phase 6 Qdrant Schema Reference

Dense collections use cosine similarity, explicit vector-size validation, versioned collection names, configurable HNSW construction/search values, and payload indexes for domain, document ID, source-date ordinal, and chunking configuration fingerprint. Schema mismatches require a version bump or rebuild rather than silent reuse.
