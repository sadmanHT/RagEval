from __future__ import annotations

from pathlib import Path

import pytest

from rageval.cleaning import CleaningConfig, clean_parsed_document
from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import Domain, ElementType

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"


def _manifest_item(name: str):
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    return next(item for item in manifest.documents if Path(item.relative_path).name == name)


@pytest.mark.parametrize(
    ("name", "domain"),
    [
        ("financial_report.pdf", Domain.FINANCIAL),
        ("msa.docx", Domain.LEGAL),
        ("paper.html", Domain.RESEARCH),
    ],
)
def test_domain_fixtures_clean_without_losing_source_traceability(
    name: str,
    domain: Domain,
) -> None:
    item = _manifest_item(name)
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED),
    )

    cleaned = clean_parsed_document(parsed)

    assert cleaned.document.domain is domain
    assert cleaned.stats.elements_in == len(parsed.elements)
    assert cleaned.stats.elements_out <= cleaned.stats.elements_in
    assert cleaned.source_parser_config_fingerprint == parsed.config_fingerprint
    source_ids = {element.element_id for element in parsed.elements}
    assert all(element.metadata["source_element_id"] in source_ids for element in cleaned.elements)
    assert all(element.document_id == item.record.document_id for element in cleaned.elements)


def test_financial_table_fixture_retains_structured_table_metadata() -> None:
    item = _manifest_item("financial_table.pdf")
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
    )
    source_tables = {
        element.element_id: element
        for element in parsed.elements
        if element.kind is ElementType.TABLE
    }
    assert source_tables

    cleaned = clean_parsed_document(parsed)
    cleaned_tables = [element for element in cleaned.elements if element.kind is ElementType.TABLE]

    assert len(cleaned_tables) == len(source_tables)
    assert cleaned.stats.tables_preserved == len(source_tables)
    for table in cleaned_tables:
        source = source_tables[str(table.metadata["source_element_id"])]
        assert table.metadata["table_html"] == source.metadata["table_html"]
        assert table.metadata["source_offset"] == source.metadata["source_offset"]
        assert table.page_number == source.page_number


def test_research_fixture_preserves_answer_bearing_retrieval_statements() -> None:
    item = _manifest_item("paper.html")
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED),
    )
    cleaned = clean_parsed_document(parsed, config=CleaningConfig())
    text = " ".join(element.text for element in cleaned.elements)

    assert "Hybrid retrieval combines lexical and dense signals." in text
    assert "Reciprocal Rank Fusion can combine rankings without score calibration." in text
