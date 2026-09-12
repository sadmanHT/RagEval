from __future__ import annotations

from pathlib import Path

from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import ElementType


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"


class FixtureOCR:
    @property
    def name(self) -> str:
        return "fixture-ocr"

    def extract_page_text(self, path: Path, page_number: int, *, dpi: int) -> str:
        assert path.name == "scanned_notice.pdf"
        assert page_number == 1
        assert dpi >= 72
        return "Scanned legal notice requires OCR fallback."


def _manifest_item(name: str):
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    return next(item for item in manifest.documents if Path(item.relative_path).name == name)


def test_pdf_fixture_preserves_page_provenance_and_stable_ids() -> None:
    item = _manifest_item("financial_report.pdf")
    config = ParserConfig(ocr_mode=OCRMode.DISABLED)
    first = parse_corpus_document(item, FIXTURE_ROOT, config=config)
    second = parse_corpus_document(item, FIXTURE_ROOT, config=config)

    assert first.elements
    assert [element.element_id for element in first.elements] == [
        element.element_id for element in second.elements
    ]
    assert all(
        element.page_number is not None
        for element in first.elements
        if element.kind is not ElementType.PAGE_BREAK
    )
    assert all(
        element.metadata["parser_version"] == config.parser_version
        for element in first.elements
    )


def test_docx_fixture_emits_normalized_elements() -> None:
    item = _manifest_item("msa.docx")
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED),
    )
    assert parsed.elements
    assert all(element.document_id == item.record.document_id for element in parsed.elements)
    assert any(element.kind in {ElementType.TITLE, ElementType.TEXT} for element in parsed.elements)


def test_html_fixture_emits_section_aware_elements() -> None:
    item = _manifest_item("paper.html")
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED),
    )
    assert parsed.elements
    assert any(element.kind is ElementType.TITLE for element in parsed.elements)
    assert any(element.metadata.get("section_hint") for element in parsed.elements)


def test_table_pdf_keeps_table_identity_when_detectable() -> None:
    item = _manifest_item("financial_table.pdf")
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED, detect_tables=True),
    )
    tables = [element for element in parsed.elements if element.kind is ElementType.TABLE]
    assert tables
    assert all("table_html" in element.metadata for element in tables)


def test_scanned_pdf_exercises_explicit_ocr_fallback() -> None:
    item = _manifest_item("scanned_notice.pdf")
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.FALLBACK, ocr_min_native_chars=20),
        ocr_adapter=FixtureOCR(),
    )
    assert parsed.used_ocr
    ocr = [element for element in parsed.elements if element.kind is ElementType.OCR_TEXT]
    assert len(ocr) == 1
    assert ocr[0].metadata["ocr_adapter"] == "fixture-ocr"
    assert ocr[0].page_number == 1
