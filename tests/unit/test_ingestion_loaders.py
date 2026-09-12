from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rageval.core.errors import DocumentParseError, UnsupportedSourceError
from rageval.ingestion.loaders import parse_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import DocumentRecord, Domain, ElementType, SourceType


def _record(path: Path, source_type: SourceType) -> DocumentRecord:
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return DocumentRecord(
        document_id=f"doc_{checksum[:32]}",
        source_uri=f"file:///{path.name}",
        source_type=source_type,
        domain=Domain.RESEARCH,
        checksum_sha256=checksum,
    )


def test_html_parse_is_idempotent_with_stable_element_ids(tmp_path: Path) -> None:
    path = tmp_path / "note.html"
    path.write_text(
        "<html><body><h1>Heading</h1><p>Body text.</p><ul><li>One</li></ul></body></html>",
        encoding="utf-8",
    )
    record = _record(path, SourceType.HTML)
    config = ParserConfig(ocr_mode=OCRMode.DISABLED)

    first = parse_document(path, record, config=config)
    second = parse_document(path, record, config=config)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert [item.kind for item in first.elements] == [
        ElementType.TITLE,
        ElementType.TEXT,
        ElementType.LIST_ITEM,
    ]
    assert first.elements[1].metadata["section_hint"] == "Heading"


def test_source_type_extension_mismatch_is_typed(tmp_path: Path) -> None:
    path = tmp_path / "note.html"
    path.write_text("<p>Hello</p>", encoding="utf-8")
    record = _record(path, SourceType.PDF)

    with pytest.raises(UnsupportedSourceError, match="does not match"):
        parse_document(path, record, config=ParserConfig(ocr_mode=OCRMode.DISABLED))


def test_corrupt_pdf_is_typed(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"not a pdf")
    record = _record(path, SourceType.PDF)

    with pytest.raises(DocumentParseError, match="cannot open PDF"):
        parse_document(path, record, config=ParserConfig(ocr_mode=OCRMode.DISABLED))
