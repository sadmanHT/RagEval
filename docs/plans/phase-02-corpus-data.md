# Phase 2 — Corpus Contracts, Fixtures, Data Governance & Evaluation Split

## Mission

Define exactly what enters RAG-Eval and make provenance, domains, file identity, and the
development/evaluation boundary deterministic before document parsing begins.

## Deliverables

- Versioned corpus manifest contracts for financial, legal, and research documents.
- Recursive discovery of PDF, DOCX, and HTML sources without parsing their contents.
- Streaming SHA-256 checksums and deterministic document IDs.
- Duplicate evidence grouped by checksum.
- Strict development/evaluation leakage detection by checksum and document identity.
- Stable corpus fingerprint independent of discovery ordering and scan timestamps.
- Evaluation-record wrapper plus deterministic evaluation-dataset fingerprinting.
- Manifest JSON read/write/validation and source checksum verification.
- `python -m rageval.corpus.cli` / `scripts/corpus_manifest.py` CLI.
- Real miniature fixtures: text PDF, table PDF, image-only scanned PDF, DOCX, and HTML.
- Unit and integration coverage plus all Phase 1 regression gates.

## Corpus layout contract

```text
<root>/
  development|evaluation/
    financial|legal|research/
      <document.pdf|document.docx|document.html>
```

The split and domain are therefore explicit data-governance inputs rather than heuristics
derived from document contents.

## Acceptance gate

Phase 2 is complete only when a fixture corpus can be scanned, serialized, reloaded,
fingerprinted, source-validated, and proven leakage-safe while the complete Phase 1 quality,
service-integration, smoke, and regression suites remain green.
