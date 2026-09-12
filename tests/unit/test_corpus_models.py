from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError as PydanticValidationError

from rageval.corpus.models import CorpusDocument, DatasetSplit, SourceLocator
from rageval.models import DocumentRecord, Domain, SourceType


def _record() -> DocumentRecord:
    return DocumentRecord(
        document_id="doc_12345678",
        source_uri="file:///development/financial/report.pdf",
        source_type=SourceType.PDF,
        domain=Domain.FINANCIAL,
        checksum_sha256="a" * 64,
    )


def test_source_locator_rejects_inverted_page_range() -> None:
    with pytest.raises(PydanticValidationError, match="page_end must be"):
        SourceLocator(page_start=4, page_end=2)


def test_source_locator_rejects_page_end_without_start() -> None:
    with pytest.raises(PydanticValidationError, match="page_end requires page_start"):
        SourceLocator(page_end=2)


def test_corpus_document_round_trip_preserves_governance_metadata() -> None:
    document = CorpusDocument(
        record=_record(),
        relative_path="development/financial/report.pdf",
        logical_title="Quarterly Report",
        split=DatasetSplit.DEVELOPMENT,
        size_bytes=1234,
        source_date=date(2026, 6, 30),
        parser_version="unparsed",
        tenant_id="tenant-a",
        security_tags=("internal", "finance"),
        locator=SourceLocator(page_start=1, page_end=3, section_hint="Results"),
    )

    restored = CorpusDocument.model_validate_json(document.model_dump_json())
    assert restored == document
    assert restored.record.ingested_at.tzinfo is not None


def test_corpus_document_rejects_unknown_metadata_field() -> None:
    with pytest.raises(PydanticValidationError):
        CorpusDocument(
            record=_record(),
            relative_path="development/financial/report.pdf",
            logical_title="Quarterly Report",
            split=DatasetSplit.DEVELOPMENT,
            size_bytes=1,
            unexpected="not-allowed",
        )
