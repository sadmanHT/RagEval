# Phase 3 — Document Loading, Parsing & OCR

## Mission

Implement reliable structured extraction for PDF, DOCX, and HTML while preserving the source
coordinates needed by later chunking, retrieval, citations, table handling, and failure analysis.

## Implemented contract

- Project-owned `DocumentElement` remains the ingestion boundary; third-party parser objects never
  leave `rageval.ingestion`.
- PDF parsing uses PyMuPDF for ordered text blocks, page coordinates, table detection, and rendering.
- DOCX parsing uses python-docx while retaining paragraph/table order, style hints, headers/footers,
  explicit page breaks, and table identity.
- HTML parsing uses BeautifulSoup and maps headings, text, lists, tables, captions, headers, footers,
  and explicit page-break markers into normalized elements.
- OCR is explicit through an `OCRAdapter` protocol. The default local implementation renders the
  requested PDF page with PyMuPDF and invokes Tesseract through pytesseract.
- Parser configuration is immutable/versioned and fingerprinted. Element IDs include document,
  ordinal, element type, text, page number, and parser-config fingerprint for idempotence.
- Batch parsing returns successes and typed per-file failures without aborting on the first bad file.
- The debug CLI can parse one file or a filtered corpus manifest subset and writes JSON only; it
  performs no indexing.

## Acceptance gate

Phase 3 is complete only after PDF/DOCX/HTML fixture parsing, explicit OCR fallback, table identity,
provenance/idempotence, corrupt/unsupported input, batch partial failure, CLI behavior, all prior
Phase 1–2 tests, static checks, local service smoke, and a dedicated Tesseract CI job pass together.
