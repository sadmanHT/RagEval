# Phase 5 Completion Report

## Status

Implementation accepted on the Phase 5 branch. Merge is pending the final documentation-head CI
run. The accepted implementation head is
`70ed3b255bafcd64128a9ce0b88a985bedaf50be` and GitHub Actions run `34707147506` completed the
quality, integration/ablation/regression, and installed-Tesseract OCR jobs successfully.

Phase 5 does **not** claim a globally optimal chunking strategy. The committed fixture corpus is
small enough that the 256/512/1024 fixed configurations and the local diagnostic semantic baseline
produce the same chunk counts. Strategy preference must come from later retrieval/evaluation
ablations on representative data.

## Implemented scope

Phase 5 adds a project-owned chunking layer that consumes Phase 4 `CleanedDocument` values and emits
the existing shared `Chunk` contract through one asynchronous `ChunkingEngine` interface.

Implemented behavior:

- reference fixed-token configurations for 256/32, 512/64, and 1024/128 size/overlap;
- semantic sentence-boundary chunking with an injected `EmbeddingProvider` and similarity policy;
- cosine similarity as the default semantic policy;
- deterministic `LocalHashEmbeddingProvider` for offline mechanics/fixture evidence only;
- table-aware handling that keeps complete small tables together;
- oversized table splitting only on whole row groups, with configured header repetition;
- table row/cell boundaries, page coordinates, source offsets, bounding boxes, and source
  `table_html` retained as metadata where Phase 3 supplied them;
- oversized atomic table rows remain whole even when they exceed a configured token target rather
  than creating orphaned cells;
- practical legal numbered-clause boundaries and configurable section-hint boundaries;
- deterministic chunk IDs using document ID, ordinal, configuration fingerprint, and chunk text;
- immutable versioned `ChunkingConfig` and deterministic behavior-complete fingerprinting;
- chunk metadata containing strategy, domain, tokenizer, source pages, cleaned element IDs,
  Phase 4 source element IDs, element kinds, overlap evidence, table/section flags, and source
  cleaning fingerprint;
- debug parse -> clean -> chunk JSON CLI without indexing;
- machine-readable ablation report with deterministic dataset fingerprint, chunk count, token
  distributions, measured overlap, table fragmentation count, and provenance coverage per
  strategy/domain;
- permanent CI execution of the chunking fixture ablation alongside Phase 4 cleaning statistics.

## Files and boundaries

Primary production additions:

- `src/rageval/chunking/models.py`
- `src/rageval/chunking/tokenizer.py`
- `src/rageval/chunking/providers.py`
- `src/rageval/chunking/engine.py`
- `src/rageval/chunking/ablation.py`
- `src/rageval/chunking/cli.py`
- `src/rageval/chunking/__init__.py`

Verification/evidence additions and updates:

- `tests/unit/test_chunking.py`
- `tests/integration/test_chunking_fixtures.py`
- `tests/unit/test_imports.py`
- `scripts/chunking_fixture_report.py`
- `.github/workflows/ci.yml`
- `docs/plans/phase-05-chunking-ablation.md`
- `docs/phases/phase-05-report.md`

The shared `Chunk` model was deliberately reused without a parallel Phase 5 chunk schema. New
strategy/provenance fields live in stable typed configuration/result contracts and chunk metadata,
so later retrieval phases can consume the existing public chunk boundary.

## Architecture decisions

### Chunking begins after cleaning

Phase 5 consumes `CleanedDocument.elements`; it does not re-open PDFs, DOCX, HTML, or OCR artifacts.
Every emitted chunk records the source cleaning configuration fingerprint and the cleaned/source
element IDs that contributed content. This keeps parser/cleaner/chunker responsibilities separate.

### One dispatch boundary for all strategies

`ChunkingEngine` selects fixed or semantic behavior from `ChunkingConfig`, while table awareness,
section awareness, legal boundaries, deterministic IDs, and provenance apply through the common
boundary. Downstream code does not need a separate interface for every strategy.

### Token counts use a deterministic offline baseline

Phase 5 uses `WhitespaceTokenizer` (`whitespace-v1`) as the deterministic local baseline so exact
size/overlap mechanics can be tested without a hosted tokenizer dependency. These counts must not
be misrepresented as provider-model token counts. A later embedding/generation provider may require
a provider-specific tokenizer adapter while preserving the `Tokenizer` boundary.

### Semantic mechanics are provider-abstracted

The semantic chunker uses the existing async `EmbeddingProvider` protocol and a separate
`SimilarityPolicy`. Unit tests inject known vectors to force exact split points. The committed
fixture ablation uses `LocalHashEmbeddingProvider`, a deterministic hashed bag-of-words adapter.
That run validates semantic chunking mechanics and provenance offline; it is not evidence about
OpenAI, Cohere, or any learned semantic embedding model.

### Tables favor interpretability over a hard size cap

Small tables remain intact. Oversized tables are grouped by complete source rows and configured
headers are repeated. A single oversized row remains atomic even if its token count exceeds the
configured target because splitting cells would create uninterpretable fragments. Source
`table_html` is retained as source metadata; Phase 5 does not synthesize semantically re-sliced HTML.

### Fixture page provenance follows the source representation

PDF elements can contribute page numbers, while HTML elements legitimately may have no page number.
The integration gate compares chunk pages to the actual non-null source pages instead of inventing
page coordinates for page-less formats.

## Verification evidence

Accepted implementation head: `70ed3b255bafcd64128a9ce0b88a985bedaf50be`.

GitHub Actions run: `34707147506`.

Quality:

- `ruff check .` — passed;
- `ruff format --check .` — passed, 79 files already formatted;
- `mypy src` — passed, no issues in 36 source files;
- `pytest -q tests/unit` — 66 passed.

Integration/regression:

- `docker compose config` — passed;
- Qdrant and Redis startup/readiness — passed;
- `pytest -q tests/integration` — 20 passed, 1 skipped;
- the single regular-integration skip remains the explicit local-OCR-only test because that runner
  does not install Tesseract;
- `python scripts/cleaning_fixture_report.py` — passed, preserving Phase 4 evidence;
- `python scripts/chunking_fixture_report.py` — passed;
- `python -m rageval.smoke` — passed;
- `pytest -q` — 86 passed, 1 skipped (the same local-OCR-only test);
- Compose teardown including volumes — passed.

Dedicated OCR regression:

- Ubuntu Tesseract 5.3.4 installed successfully;
- `pytest -q -m local_ocr tests/integration/test_local_ocr.py` — 1 passed.

No hosted embedding, reranking, generation, observability, or experiment-tracker credentials are
needed for deterministic Phase 5 acceptance. No hosted-provider result is claimed.

## Fixture ablation evidence

`python scripts/chunking_fixture_report.py` produced a machine-readable report with dataset
fingerprint:

`de9ac8a849c05782102c91800a4a58acd00c21564c0966ea160dac1b72643d9b`

The committed fixture corpus contains five cleaned documents for this report: two financial, two
legal (including deterministic OCR content), and one research document. The report labels its
semantic embedding evidence `local-hash-diagnostic-only`.

For **each** of fixed 256/32, fixed 512/64, fixed 1024/128, and semantic on this small fixture
corpus:

- financial: 2 documents -> 3 chunks; token lengths min 3, max 22, mean 14.0, p50 17, p95 22;
- legal: 2 documents -> 3 chunks; token lengths min 6, max 21, mean 14.6667, p50 17, p95 21;
- research: 1 document -> 1 chunk; token length 19;
- measured mean overlap is 0.0 for every domain/configuration because no non-table prose fixture is
  large enough to cross the reference fixed window sizes;
- provenance coverage is 1.0 for every domain/configuration;
- incorrect table fragmentation count is 0 for every domain/configuration.

These identical fixture-level counts are **not** an optimization result. They demonstrate that all
reference strategies work through one boundary with complete provenance and table-aware behavior,
but the fixture corpus is too small to rank strategies or exercise the documented fixed-window
overlap defaults at corpus scale. Exact overlap behavior is instead covered by deterministic unit
tests using inputs larger than each configured window.

## Failure/repair evidence

The first CI run correctly rejected Phase 5 for Ruff import ordering and an integration assertion
that incorrectly required non-empty page numbers for the HTML research fixture. The implementation
was repaired by applying canonical import ordering and changing the page-provenance assertion to
compare chunk pages with the source elements' actual non-null pages. No behavior or gate was
weakened.

A following CI run cleared lint but identified three canonical formatter differences. Those files
were reformatted exactly as Ruff requested, and the entire cumulative suite was rerun. The accepted
run `34707147506` then passed quality, integration/ablation/regression, and real installed-Tesseract
OCR.

No tests, assertions, lint rules, type-check settings, cleaning gates, service checks, or prior-phase
regressions were deleted or broadly skipped.

## Known limitations

- The target production-scale roughly 12,000-document corpus is not present in the repository, so
  no production chunk distribution or preferred strategy is claimed.
- The committed source fixtures are deliberately small; they do not differentiate the three fixed
  reference sizes and produce zero measured fixed overlap at fixture scale.
- `WhitespaceTokenizer` is a deterministic mechanics baseline, not a model/provider tokenizer.
- `LocalHashEmbeddingProvider` validates the semantic pipeline offline but is not a learned semantic
  model and cannot establish semantic retrieval quality.
- No hosted semantic-embedding comparison was run because provider credentials/model validation are
  outside deterministic Phase 5 acceptance.
- A single oversized table row can exceed the target chunk size to avoid orphaning cells.
- Source table HTML is retained for provenance; row-group chunks do not currently synthesize new
  HTML fragments for each split group.
- Section/legal-boundary rules are conservative heuristics and should be evaluated against retrieval
  recall/precision before they are tuned aggressively.
- GitHub Actions still reports the external Node 20 deprecation warning for checkout/setup-python;
  it does not fail the gates.

## Phase 6 handoff

Phase 6 should implement embedding providers, Qdrant collection/index management, payload schemas,
batch/retry behavior, and dense retrieval over Phase 5 `Chunk` outputs. Index identity must include
or record the chunking configuration fingerprint so multiple ablation collections remain
reproducible. Qdrant payloads should retain document/domain/source page/source element/table
metadata needed for filtering, citation attribution, and evaluation. Phase 6 must not silently
select a globally winning chunk configuration from this Phase 5 fixture report.
