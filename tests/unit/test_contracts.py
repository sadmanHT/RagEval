import pytest
from pydantic import ValidationError

from rageval.models import Chunk, DocumentRecord, Domain, SourceType


def test_document_record_round_trip() -> None:
    record = DocumentRecord(
        document_id="doc_12345678",
        source_uri="file:///report.pdf",
        source_type=SourceType.PDF,
        domain=Domain.FINANCIAL,
        checksum_sha256="a" * 64,
        metadata={"year": 2024},
    )

    restored = DocumentRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Chunk(
            chunk_id="chk_12345678",
            document_id="doc_12345678",
            ordinal=0,
            text="content",
            token_count=1,
            config_fingerprint="f" * 64,
            unexpected=True,
        )


def test_checksum_shape_is_validated() -> None:
    with pytest.raises(ValidationError):
        DocumentRecord(
            document_id="doc_12345678",
            source_uri="file:///report.pdf",
            source_type=SourceType.PDF,
            domain=Domain.FINANCIAL,
            checksum_sha256="not-a-sha",
        )
