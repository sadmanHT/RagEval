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

Detailed evidence is in `docs/phases/phase-03-report.md`.

### Phase 4 — Cleaning, normalization, deduplication, and metadata integrity

Merged to `main` as PR #4 at commit `4366bb0f5a5a7a4f7184eb24fdf744d9eddfb502` and revalidated
post-merge in GitHub Actions run `34705921835`. The merge commit passed quality,
integration/regression/statistics, and the dedicated installed-Tesseract OCR job.

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

Acceptance evidence: Ruff and formatter passed; strict mypy passed on 29 source files; 53 unit
tests passed; 14 regular integration tests passed with one intentional local-OCR-only skip; the
package smoke passed; the complete regression suite passed 67 tests with the same one skip; and the
dedicated local-OCR job installed Tesseract 5.3.4 and passed its real OCR test independently.
Qdrant/Redis readiness and clean Compose teardown also passed.

Measured cleaning evidence distinguishes preservation from reduction. The inherited five fixtures
were already clean and correctly remained 13 -> 13 elements and 719 -> 719 characters. The noisy
Phase 4 goldens reduced 37 -> 13 elements and 1,239 -> 636 characters while removing 603
characters, 6 duplicate boilerplate elements, and 24 total boilerplate/page-artifact elements; the
financial structured table remained preserved. Detailed evidence is in
`docs/phases/phase-04-report.md`.

### Phase 5 — Chunking engine, table awareness, and ablation harness

Merged to `main` as PR #5 at commit `33ded41494e3573552e9b3ee4dfa1371e8b5abaa` from final
validated PR head `85e84ce10b8ab81b7c8a76232a7cd5352c33a6f6`. Post-merge GitHub Actions run
`34707378361` passed quality, integration/cleaning/chunking-ablation/smoke/full regression, and the
dedicated installed-Tesseract OCR job. The later documentation-only `main` commits also repeated
all three gates successfully; closure evidence is recorded in `docs/phases/phase-05-postmerge.md`.

Implemented scope:
- one async `ChunkingEngine` for fixed 256/32, 512/64, 1024/128, and semantic strategies;
- immutable versioned chunking configuration and deterministic configuration fingerprints;
- exact fixed-window overlap plus provider-injected semantic sentence-boundary splitting;
- deterministic local hash embeddings for offline semantic mechanics only, not learned-model
  quality claims;
- table-aware small-table preservation and whole-row oversized-table grouping with repeated headers;
- source page/element/table coordinates, Phase 4 cleaning fingerprint, and direct source-element
  provenance on every chunk;
- practical legal-clause and configurable section-aware boundaries;
- deterministic chunk IDs through the existing shared `Chunk` contract;
- debug parse -> clean -> chunk CLI without indexing;
- machine-readable per-strategy/domain ablation statistics for chunk counts, token lengths, overlap,
  table fragmentation, and provenance coverage;
- a permanent CI chunking-ablation gate plus cumulative Phase 1–4 regression coverage.

Acceptance evidence: Ruff and formatter passed with 79 files formatted; strict mypy passed on 36
source files; 66 unit tests passed; regular integration passed 20 tests with one intentional
local-OCR-only skip; the full cumulative suite passed 86 tests with that same skip; Qdrant/Redis
readiness, cleaning statistics, chunking ablation, package smoke, and clean Compose teardown passed;
the dedicated OCR job installed Tesseract 5.3.4 and passed the real OCR test.

Fixture ablation dataset fingerprint:
`de9ac8a849c05782102c91800a4a58acd00c21564c0966ea160dac1b72643d9b`.
All four reference strategies achieved 1.0 source-element provenance coverage and zero incorrect
table-fragmentation findings on the committed fixture corpus. The corpus is too small to rank the
strategies: fixed 256/512/1024 and the local diagnostic semantic baseline produced identical chunk
counts per domain and zero measured fixed overlap at fixture scale. No globally preferred strategy
is claimed. Detailed evidence is in `docs/phases/phase-05-report.md`.

## Next phase

### Phase 6 — Embeddings, Qdrant indexing, and dense retrieval

Phase 6 must consume Phase 5 `Chunk` outputs without re-chunking, preserve each chunk's deterministic
ID and chunking configuration fingerprint in index identity/payload metadata, implement embedding
providers behind the existing protocol, and add reproducible Qdrant collection/index management and
dense retrieval. It must retain source/domain/page/element/table provenance needed for filters,
citations, evaluation attribution, and safe rebuilds. Phase 5 fixture statistics must not be used to
silently hard-code one winning chunk configuration.

## Later phases

Sparse retrieval, fusion/query expansion, reranking/multi-hop, grounded generation, evaluation,
serving, observability/deployment hardening, and final release validation remain intentionally
deferred to their respective later phases.
