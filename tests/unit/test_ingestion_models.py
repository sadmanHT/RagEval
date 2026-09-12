from __future__ import annotations

import pytest

from rageval.ingestion.models import BatchParseResult, OCRMode, ParseFailure, ParserConfig


def test_parser_config_is_versioned_and_strict() -> None:
    config = ParserConfig(ocr_mode=OCRMode.DISABLED)
    assert config.schema_version == "1.0"
    assert config.parser_version == "phase3-1.0"


def test_batch_failure_policy_is_explicit() -> None:
    result = BatchParseResult(
        failures=(
            ParseFailure(
                document_id="doc_12345678",
                relative_path="development/legal/bad.docx",
                error_type="DocumentParseError",
                message="broken",
            ),
        )
    )
    assert result.exceeds_failure_policy(max_failures=0)
    assert not result.exceeds_failure_policy(max_failures=1)
    with pytest.raises(ValueError, match="non-negative"):
        result.exceeds_failure_policy(max_failures=-1)
