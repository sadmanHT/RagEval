# Implementation State

## Completed

### Phase 1 — Repository foundation, contracts, and quality gates

Merged to `main` and revalidated after merge. The repository has strict shared contracts,
provider protocols/fakes, safe settings/logging, deterministic IDs, typed errors, Qdrant/Redis
Compose infrastructure, canonical verification commands, and GitHub Actions quality/integration
jobs.

### Phase 2 — Corpus contracts, fixtures, data governance, and evaluation split

Merged to `main` and revalidated after merge. Phase 2 established versioned corpus/evaluation
contracts, deterministic identities/fingerprints, duplicate/leakage protection, manifest tooling,
and the mixed-format fixture corpus used by later phases. Detailed evidence is in
`docs/phases/phase-02-report.md`.

### Phase 3 — Document loading, parsing, and OCR

Merged to `main` as PR #3 at commit `c898bdd8b91170cf3b371b15620f7203d79ef208` and revalidated
post-merge in GitHub Actions run `34704484873`. Quality, service-backed integration/regression, and
the dedicated installed-Tesseract OCR job all completed successfully on the merge commit.

Implemented scope:
- normalized PDF/DOCX/HTML extraction through project-owned `DocumentElement` contracts;
- page/source coordinates, section hints, headers/footers, lists, captions, page breaks, and table
  identity/HTML where available;
- versioned parser configuration plus deterministic parser fingerprints and element IDs;
- explicit injectable OCR fallback with local Tesseract implementation and OCR provenance;
- single-file and corpus-subset debug JSON CLI without indexing;
- typed corrupt/unsupported input handling and per-file batch failure collection;
- golden mixed-format fixture tests, a dedicated installed-Tesseract CI job, and cumulative
  Phase 1–2 regression verification.

Branch acceptance evidence: Ruff and Ruff formatting passed; strict mypy passed on 25 source files;
42 unit tests passed; regular integration passed 9 tests with the local-OCR-only test intentionally
skipped there; full cumulative regression passed 51 tests with that same one skip; the dedicated
Tesseract job installed the OCR binary and passed the OCR test independently; Qdrant/Redis
readiness, package smoke, and clean Compose teardown all passed. The final evidence head repeated
the three CI gates successfully before merge, and the merge commit repeated them successfully on
`main`. Detailed evidence is in `docs/phases/phase-03-report.md`.

## Accepted on branch; repository closure pending

### Phase 4 — Cleaning, normalization, deduplication, and metadata integrity

Branch: `phase-04-cleaning-normalization`.

Implementation/evidence head `097d9a27b335bf125a688c90ca10be42cb7f2c00` passed GitHub Actions
run `34705690248`: Ruff and formatter passed, strict mypy passed on 29 source files, 53 unit tests
passed, 14 regular integration tests passed with one intentional local-OCR-only skip, the package
smoke passed, and the full regression suite passed 67 tests with that same one skip. The dedicated
local-OCR job installed Tesseract 5.3.4 and passed its real OCR fixture test independently. Qdrant
and Redis readiness plus clean Compose teardown passed.

Implemented scope:
- deterministic Unicode/control/whitespace/hyphenation normalization that retains meaningful
  punctuation and numeric syntax;
- cross-page repeated header/footer/page-number suppression rather than blind deletion;
- conservative configurable near-duplicate boilerplate detection with typed removal evidence;
- preservation of table row/cell delimiters and structured metadata (`table_html`, coordinates,
  source offsets, sections, and page provenance);
- deterministic cleaned element IDs linked back through `source_element_id`;
- immutable cleaning configuration plus deterministic configuration fingerprint;
- per-document cleaning statistics and a permanent CI statistics command;
- financial/legal/research noisy golden cleaning tests plus inherited Phase 2/3 fixture
  preservation tests.

Measured CI evidence distinguishes preservation from reduction. The inherited five fixtures were
already clean and correctly remained 13 -> 13 elements and 719 -> 719 characters. The dedicated
noisy Phase 4 goldens reduced 37 -> 13 elements and 1,239 -> 636 characters while removing 603
characters, 6 duplicate boilerplate elements, and 24 total boilerplate/page-artifact elements; the
financial structured table remained preserved. Detailed evidence is in
`docs/phases/phase-04-report.md`.

Phase 4 is not repository-complete until the final documentation head passes all PR checks, PR #4
is merged, and the merge commit passes quality, integration/regression/statistics, and installed-
Tesseract validation again on `main`.

## Next phase after Phase 4 closure

### Phase 5 — Chunking ablation and table-aware boundaries

Phase 5 must consume cleaned Phase 4 elements, preserve source-element provenance and table
boundaries, and implement controlled fixed-token 256/512/1024 plus semantic chunking strategies.
No preferred chunking strategy may be claimed without measured ablation evidence.

## Later phases

Embeddings/dense retrieval, sparse retrieval, fusion/query expansion, reranking/multi-hop,
grounded generation, evaluation, serving, observability/deployment hardening, and final release
validation remain intentionally deferred to their respective later phases.
