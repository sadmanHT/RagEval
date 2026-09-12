from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from rageval.corpus.manifest import scan_corpus
from rageval.ingestion.loaders import parse_corpus_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import ElementType


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"


@pytest.mark.local_ocr
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract binary is not installed")
def test_image_only_pdf_parses_with_local_tesseract() -> None:
    manifest = scan_corpus(FIXTURE_ROOT).manifest
    item = next(
        candidate
        for candidate in manifest.documents
        if Path(candidate.relative_path).name == "scanned_notice.pdf"
    )
    parsed = parse_corpus_document(
        item,
        FIXTURE_ROOT,
        config=ParserConfig(ocr_mode=OCRMode.FALLBACK, ocr_min_native_chars=20),
    )
    ocr = [element for element in parsed.elements if element.kind is ElementType.OCR_TEXT]
    assert parsed.used_ocr
    assert ocr
    assert len(ocr[0].text.strip()) >= 5
