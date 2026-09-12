from __future__ import annotations

from pathlib import Path

import pytest

from rageval.chunking import (
    ChunkingConfig,
    ChunkingEngine,
    ChunkStrategy,
    LocalHashEmbeddingProvider,
    reference_chunking_config,
    run_chunking_ablation,
)
from rageval.cleaning import clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Domain, ElementType

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"


def _manifest_item(name: str):
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    return next(item for item in manifest.documents if Path(item.relative_path).name == name)


def _clean_fixture(name: str):
    item = _manifest_item(name)
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
    )
    return clean_parsed_document(parsed)


@pytest.mark.parametrize(
    ("name", "domain"),
    [
        ("financial_report.pdf", Domain.FINANCIAL),
        ("msa.docx", Domain.LEGAL),
        ("paper.html", Domain.RESEARCH),
    ],
)
@pytest.mark.asyncio
async def test_domain_fixtures_chunk_with_full_provenance(
    name: str,
    domain: Domain,
) -> None:
    cleaned = _clean_fixture(name)
    result = await ChunkingEngine().chunk(
        cleaned,
        config=reference_chunking_config(ChunkStrategy.FIXED_512),
    )

    assert result.document.domain is domain
    assert result.chunks
    expected = {
        element.element_id
        for element in cleaned.elements
        if element.kind is not ElementType.PAGE_BREAK and element.text.strip()
    }
    covered = {
        element_id
        for chunk in result.chunks
        for element_id in chunk.metadata["cleaned_element_ids"]
    }
    assert covered == expected

    expected_pages = {
        element.page_number
        for element in cleaned.elements
        if element.kind is not ElementType.PAGE_BREAK
        and element.text.strip()
        and element.page_number is not None
    }
    observed_pages = {
        page
        for chunk in result.chunks
        for page in chunk.metadata["source_pages"]
        if isinstance(page, int)
    }
    assert observed_pages == expected_pages


@pytest.mark.asyncio
async def test_financial_table_fixture_is_table_aware() -> None:
    cleaned = _clean_fixture("financial_table.pdf")
    source_tables = [
        element for element in cleaned.elements if element.kind is ElementType.TABLE
    ]
    assert source_tables

    result = await ChunkingEngine().chunk(
        cleaned,
        config=ChunkingConfig(
            strategy=ChunkStrategy.FIXED_256,
            chunk_size=6,
            overlap=1,
        ),
    )
    table_chunks = [
        chunk for chunk in result.chunks if chunk.metadata.get("table_row_group") is True
    ]

    assert table_chunks
    for chunk in table_chunks:
        assert chunk.metadata["source_table_id"]
        assert chunk.metadata["source_table_html"]
        assert chunk.metadata["source_offset"] is not None
        assert chunk.metadata["source_pages"]


@pytest.mark.asyncio
async def test_semantic_strategy_runs_on_research_fixture_without_hosted_credentials() -> None:
    cleaned = _clean_fixture("paper.html")
    result = await ChunkingEngine(
        embedding_provider=LocalHashEmbeddingProvider(),
    ).chunk(
        cleaned,
        config=ChunkingConfig(
            strategy=ChunkStrategy.SEMANTIC,
            chunk_size=64,
            overlap=0,
            semantic_min_tokens=4,
            semantic_max_tokens=16,
            semantic_similarity_threshold=0.25,
        ),
    )

    assert result.chunks
    assert result.metadata["embedding_provider"] == "local-hash-embedding-v1"
    text = " ".join(chunk.text for chunk in result.chunks)
    assert "Hybrid retrieval combines lexical and dense signals." in text


@pytest.mark.asyncio
async def test_fixture_corpus_ablation_covers_all_reference_strategies() -> None:
    documents = [
        _clean_fixture("financial_report.pdf"),
        _clean_fixture("financial_table.pdf"),
        _clean_fixture("msa.docx"),
        _clean_fixture("paper.html"),
    ]
    configs = tuple(reference_chunking_config(strategy) for strategy in ChunkStrategy)
    report = await run_chunking_ablation(
        documents,
        configs=configs,
        embedding_provider=LocalHashEmbeddingProvider(),
        metadata={"dataset": "phase2-3-source-fixtures-no-ocr"},
    )

    assert len(report.stats) == len(configs) * len(Domain)
    assert all(stat.provenance_coverage == 1.0 for stat in report.stats)
    assert all(stat.table_fragmentation_count == 0 for stat in report.stats)
