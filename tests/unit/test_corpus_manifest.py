from __future__ import annotations

from pathlib import Path

import pytest

from rageval.core.errors import DataLeakageError, ValidationError
from rageval.corpus.manifest import (
    assert_no_split_leakage,
    fingerprint_documents,
    read_manifest,
    scan_corpus,
    validate_manifest_files,
    write_manifest,
)
from rageval.corpus.models import CorpusDocument, DatasetSplit
from rageval.models import DocumentRecord, Domain, SourceType


def _document(*, path: str, checksum: str, split: DatasetSplit) -> CorpusDocument:
    return CorpusDocument(
        record=DocumentRecord(
            document_id=f"doc_{checksum[:16]}_{split.value}",
            source_uri=f"file:///{path}",
            source_type=SourceType.PDF,
            domain=Domain.FINANCIAL,
            checksum_sha256=checksum,
        ),
        relative_path=path,
        logical_title=Path(path).stem,
        split=split,
        size_bytes=10,
    )


def test_fingerprint_is_independent_of_document_order() -> None:
    first = _document(
        path="development/financial/a.pdf",
        checksum="a" * 64,
        split=DatasetSplit.DEVELOPMENT,
    )
    second = _document(
        path="development/financial/b.pdf",
        checksum="b" * 64,
        split=DatasetSplit.DEVELOPMENT,
    )
    assert fingerprint_documents([first, second]) == fingerprint_documents([second, first])


def test_renamed_duplicate_crossing_split_is_rejected() -> None:
    checksum = "c" * 64
    development = _document(
        path="development/financial/original.pdf",
        checksum=checksum,
        split=DatasetSplit.DEVELOPMENT,
    )
    evaluation = _document(
        path="evaluation/financial/renamed.pdf",
        checksum=checksum,
        split=DatasetSplit.EVALUATION,
    )
    with pytest.raises(DataLeakageError, match="leakage detected"):
        assert_no_split_leakage([development, evaluation])


def test_scanner_reports_duplicate_content_inside_same_split(tmp_path: Path) -> None:
    directory = tmp_path / "development" / "financial"
    directory.mkdir(parents=True)
    (directory / "first.pdf").write_bytes(b"same")
    (directory / "renamed.pdf").write_bytes(b"same")

    report = scan_corpus(tmp_path)

    assert len(report.manifest.documents) == 2
    assert len(report.manifest.duplicates) == 1
    assert report.manifest.duplicates[0].relative_paths == (
        "development/financial/first.pdf",
        "development/financial/renamed.pdf",
    )


def test_unsupported_extension_can_be_reported_or_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "development" / "research"
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("unsupported", encoding="utf-8")

    report = scan_corpus(tmp_path)
    assert report.unsupported_paths == ("development/research/notes.txt",)

    with pytest.raises(ValidationError, match="unsupported corpus files"):
        scan_corpus(tmp_path, fail_on_unsupported=True)


def test_invalid_layout_is_actionable(tmp_path: Path) -> None:
    (tmp_path / "lonely.pdf").write_bytes(b"%PDF-fixture")
    with pytest.raises(ValidationError, match="<split>/<domain>/<file>"):
        scan_corpus(tmp_path)


def test_manifest_round_trip_and_missing_file_detection(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    source = corpus / "development" / "legal" / "contract.html"
    source.parent.mkdir(parents=True)
    source.write_text("<p>contract</p>", encoding="utf-8")

    manifest = scan_corpus(corpus).manifest
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest, manifest_path)
    restored = read_manifest(manifest_path)

    assert restored.fingerprint == manifest.fingerprint
    validate_manifest_files(restored, corpus)

    source.unlink()
    with pytest.raises(ValidationError, match="source is missing"):
        validate_manifest_files(restored, corpus)


def test_manifest_rejects_tampered_fingerprint(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    source = corpus / "evaluation" / "research" / "paper.html"
    source.parent.mkdir(parents=True)
    source.write_text("<p>paper</p>", encoding="utf-8")
    manifest = scan_corpus(corpus).manifest
    path = tmp_path / "manifest.json"
    write_manifest(manifest, path)
    text = path.read_text(encoding="utf-8").replace(manifest.fingerprint, "0" * 64)
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        read_manifest(path)
