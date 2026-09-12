from __future__ import annotations

import json
from pathlib import Path

import pytest

from rageval.cleaning import CleaningConfig, clean_parsed_document
from rageval.ingestion.models import ParsedDocument
from rageval.models import DocumentElement, DocumentRecord, Domain, ElementType, SourceType

GOLDEN_PATH = Path(__file__).parents[1] / "fixtures" / "cleaning" / "golden_cases.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _parsed(case: dict[str, object]) -> ParsedDocument:
    name = str(case["name"])
    domain = Domain(str(case["domain"]))
    source_type = SourceType(str(case["source_type"]))
    raw_elements = case["elements"]
    assert isinstance(raw_elements, list)
    elements = tuple(
        DocumentElement(
            element_id=str(raw["element_id"]),
            document_id=f"doc_{name}_fixture",
            kind=ElementType(str(raw["kind"])),
            text=str(raw["text"]),
            page_number=int(raw["page_number"]) if raw["page_number"] is not None else None,
            metadata=dict(raw["metadata"]),
        )
        for raw in raw_elements
        if isinstance(raw, dict)
    )
    return ParsedDocument(
        document=DocumentRecord(
            document_id=f"doc_{name}_fixture",
            source_uri=f"fixture://cleaning/{name}",
            source_type=source_type,
            domain=domain,
            checksum_sha256="c" * 64,
        ),
        parser_name="phase4-golden-fixture",
        parser_version="1.0",
        config_fingerprint="d" * 64,
        elements=elements,
        used_ocr=False,
    )


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["name"]))
def test_per_domain_golden_cleaning(case: dict[str, object]) -> None:
    parsed = _parsed(case)
    cleaned = clean_parsed_document(parsed, config=CleaningConfig())
    expected = case["expected"]
    assert isinstance(expected, dict)

    assert cleaned.stats.elements_out == int(expected["elements_out"])
    assert cleaned.stats.elements_out < cleaned.stats.elements_in
    assert cleaned.stats.characters_removed > 0
    assert cleaned.stats.duplicates_removed == int(expected["duplicates_removed"])
    assert cleaned.stats.header_footer_removed == int(expected["header_footer_removed"])
    assert cleaned.stats.page_numbers_removed == int(expected["page_numbers_removed"])
    assert cleaned.stats.tables_preserved == int(expected["tables_preserved"])

    joined = "\n".join(element.text for element in cleaned.elements)
    retained = expected["retained_contains"]
    assert isinstance(retained, list)
    for value in retained:
        assert str(value) in joined

    source_ids = {element.element_id for element in parsed.elements}
    for element in cleaned.elements:
        assert element.metadata["source_element_id"] in source_ids
        assert element.page_number is not None

    if parsed.document.domain is Domain.FINANCIAL:
        tables = [element for element in cleaned.elements if element.kind is ElementType.TABLE]
        assert len(tables) == 1
        table = tables[0]
        assert table.text == expected["table_text"]
        assert table.metadata["bbox"] == [10.0, 20.0, 500.0, 300.0]
        assert "<table>" in str(table.metadata["table_html"])
    elif parsed.document.domain is Domain.LEGAL:
        repeated = "The parties agree that Section 7.4 survives termination."
        assert [element.text for element in cleaned.elements].count(repeated) == int(
            expected["legitimate_repeat_count"]
        )
