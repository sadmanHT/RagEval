from __future__ import annotations

from rageval.cleaning import (
    CleaningConfig,
    RemovalReason,
    clean_parsed_document,
    cleaning_config_fingerprint,
    normalize_text,
)
from rageval.ingestion.models import ParsedDocument
from rageval.models import DocumentElement, DocumentRecord, Domain, ElementType, SourceType


def _record(domain: Domain = Domain.FINANCIAL) -> DocumentRecord:
    return DocumentRecord(
        document_id="doc_1234567890abcdef",
        source_uri="file:///fixture.pdf",
        source_type=SourceType.PDF,
        domain=domain,
        checksum_sha256="a" * 64,
    )


def _element(
    ordinal: int,
    kind: ElementType,
    text: str,
    page: int | None,
    *,
    metadata: dict[str, object] | None = None,
) -> DocumentElement:
    return DocumentElement(
        element_id=f"elm_source_{ordinal:04d}",
        document_id="doc_1234567890abcdef",
        kind=kind,
        text=text,
        page_number=page,
        metadata=metadata or {},
    )


def _parsed(*elements: DocumentElement, domain: Domain = Domain.FINANCIAL) -> ParsedDocument:
    return ParsedDocument(
        document=_record(domain),
        parser_name="fixture-parser",
        parser_version="phase3-test",
        config_fingerprint="b" * 64,
        elements=elements,
        used_ocr=any(element.kind is ElementType.OCR_TEXT for element in elements),
    )


def test_normalization_preserves_financial_legal_and_research_syntax() -> None:
    text = (
        "\ufeffRevenue\u00a0was   $1,234.50  (12.5%).\n"
        "Clause 2.1 survives; see Eq. (3) and ticker BRK.B.\x00\n"
        "inter-\nnational"
    )
    normalized = normalize_text(text, kind=ElementType.TEXT, config=CleaningConfig())

    assert normalized == (
        "Revenue was $1,234.50 (12.5%). Clause 2.1 survives; see Eq. (3) "
        "and ticker BRK.B. international"
    )


def test_cleaning_config_fingerprint_is_deterministic_and_configuration_specific() -> None:
    first = cleaning_config_fingerprint(CleaningConfig())
    second = cleaning_config_fingerprint(CleaningConfig())
    changed = cleaning_config_fingerprint(CleaningConfig(dedup_similarity_threshold=0.9))

    assert first == second
    assert len(first) == 64
    assert first != changed


def test_repeated_headers_and_page_numbers_are_removed_but_body_repetition_is_preserved() -> None:
    elements: list[DocumentElement] = []
    for page in range(1, 4):
        elements.extend(
            [
                _element(page * 10, ElementType.HEADER, "ACME Annual Report 2024", page),
                _element(
                    page * 10 + 1,
                    ElementType.TEXT,
                    "Risk factors may affect reported results.",
                    page,
                ),
                _element(page * 10 + 2, ElementType.FOOTER, f"Page {page} of 3", page),
            ]
        )

    cleaned = clean_parsed_document(_parsed(*elements))

    assert [element.text for element in cleaned.elements] == [
        "Risk factors may affect reported results.",
        "Risk factors may affect reported results.",
        "Risk factors may affect reported results.",
    ]
    assert cleaned.stats.header_footer_removed == 6
    assert cleaned.stats.page_numbers_removed == 3
    assert cleaned.stats.boilerplate_removed == 6
    assert {removal.reason for removal in cleaned.removals} == {
        RemovalReason.REPEATED_HEADER,
        RemovalReason.PAGE_NUMBER,
    }


def test_deduplication_threshold_is_inclusive_and_requires_boilerplate_evidence() -> None:
    left = _element(
        1,
        ElementType.TEXT,
        "Confidential alpha beta gamma",
        1,
        metadata={"boilerplate_candidate": True},
    )
    right = _element(
        2,
        ElementType.TEXT,
        "Confidential alpha beta gamma delta",
        2,
        metadata={"boilerplate_candidate": True},
    )
    parsed = _parsed(left, right)
    shared = dict(
        dedup_min_pages=2,
        dedup_min_chars=1,
        boilerplate_markers=("confidential",),
    )

    at_boundary = clean_parsed_document(
        parsed,
        config=CleaningConfig(dedup_similarity_threshold=0.8, **shared),
    )
    above_boundary = clean_parsed_document(
        parsed,
        config=CleaningConfig(dedup_similarity_threshold=0.81, **shared),
    )

    assert len(at_boundary.elements) == 1
    assert at_boundary.stats.duplicates_removed == 1
    assert at_boundary.removals[0].reason is RemovalReason.NEAR_DUPLICATE_BOILERPLATE
    assert at_boundary.removals[0].similarity == 0.8
    assert len(above_boundary.elements) == 2
    assert above_boundary.stats.duplicates_removed == 0


def test_table_structure_and_metadata_round_trip() -> None:
    table_html = "<table><tr><td>Metric</td><td>Value</td></tr></table>"
    source = _element(
        1,
        ElementType.TABLE,
        " Metric  \t  Value \n Revenue \t $1,234.50 ",
        4,
        metadata={
            "table_html": table_html,
            "source_offset": {"page_index": 3, "table_index": 0},
            "bbox": [10.0, 20.0, 500.0, 300.0],
        },
    )

    cleaned = clean_parsed_document(_parsed(source))
    table = cleaned.elements[0]

    assert table.text == "Metric\tValue\nRevenue\t$1,234.50"
    assert table.metadata["table_html"] == table_html
    assert table.metadata["source_offset"] == {"page_index": 3, "table_index": 0}
    assert table.metadata["bbox"] == [10.0, 20.0, 500.0, 300.0]
    assert table.metadata["source_element_id"] == source.element_id
    assert cleaned.stats.tables_preserved == 1


def test_cleaned_ids_and_provenance_are_stable_and_traceable() -> None:
    source = _element(
        1,
        ElementType.OCR_TEXT,
        "  OCR\u00a0content with   spaces.  ",
        2,
        metadata={"ocr_adapter": "fixture-ocr", "source_offset": {"page_index": 1}},
    )
    parsed = _parsed(source, domain=Domain.LEGAL)

    first = clean_parsed_document(parsed)
    second = clean_parsed_document(parsed)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    cleaned = first.elements[0]
    assert cleaned.element_id != source.element_id
    assert cleaned.metadata["source_element_id"] == source.element_id
    assert cleaned.metadata["source_parser_config_fingerprint"] == parsed.config_fingerprint
    assert cleaned.metadata["source_offset"] == {"page_index": 1}
    assert cleaned.page_number == 2
    assert cleaned.text == "OCR content with spaces."
    assert first.stats.ocr_elements == 1
    assert first.stats.characters_removed > 0


def test_zero_width_only_element_is_removed_with_audit_evidence() -> None:
    source = _element(1, ElementType.TEXT, "\u200b\ufeff", 1)
    cleaned = clean_parsed_document(_parsed(source))

    assert not cleaned.elements
    assert len(cleaned.removals) == 1
    assert cleaned.removals[0].reason is RemovalReason.EMPTY_AFTER_NORMALIZATION
