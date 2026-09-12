from __future__ import annotations

from pathlib import Path

from rageval.corpus.manifest import read_manifest, scan_corpus, validate_manifest_files, write_manifest
from rageval.corpus.models import DatasetSplit
from rageval.models import Domain, SourceType


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "corpus"


def test_fixture_corpus_scan_round_trip(tmp_path: Path) -> None:
    report = scan_corpus(FIXTURE_ROOT)
    manifest = report.manifest

    assert report.unsupported_paths == ()
    assert len(manifest.documents) == 5
    assert {item.record.source_type for item in manifest.documents} == {
        SourceType.PDF,
        SourceType.DOCX,
        SourceType.HTML,
    }
    assert {item.record.domain for item in manifest.documents} == {
        Domain.FINANCIAL,
        Domain.LEGAL,
        Domain.RESEARCH,
    }
    assert {item.split for item in manifest.documents} == {
        DatasetSplit.DEVELOPMENT,
        DatasetSplit.EVALUATION,
    }

    path = tmp_path / "corpus-manifest.json"
    write_manifest(manifest, path)
    restored = read_manifest(path)
    validate_manifest_files(restored, FIXTURE_ROOT)
    assert restored.fingerprint == manifest.fingerprint


def test_fixture_files_are_real_container_formats() -> None:
    text_pdf = FIXTURE_ROOT / "development" / "financial" / "financial_report.pdf"
    table_pdf = FIXTURE_ROOT / "evaluation" / "financial" / "financial_table.pdf"
    scanned_pdf = FIXTURE_ROOT / "evaluation" / "legal" / "scanned_notice.pdf"
    docx = FIXTURE_ROOT / "development" / "legal" / "msa.docx"
    html = FIXTURE_ROOT / "evaluation" / "research" / "paper.html"

    assert text_pdf.read_bytes().startswith(b"%PDF")
    assert table_pdf.read_bytes().startswith(b"%PDF")
    assert scanned_pdf.read_bytes().startswith(b"%PDF")
    assert docx.read_bytes().startswith(b"PK")
    assert "<html" in html.read_text(encoding="utf-8").lower()
