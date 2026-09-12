"""Normalized parsing contracts for the ingestion boundary."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from rageval.models.contracts import ContractModel, DocumentElement, DocumentRecord


class OCRMode(StrEnum):
    """How OCR should be applied to PDF pages."""

    DISABLED = "disabled"
    FALLBACK = "fallback"
    ALWAYS = "always"


class ParserConfig(ContractModel):
    """Versioned settings that influence parser output and element identity."""

    schema_version: str = "1.0"
    parser_version: str = "phase3-1.0"
    ocr_mode: OCRMode = OCRMode.FALLBACK
    ocr_min_native_chars: int = Field(default=20, ge=0)
    ocr_dpi: int = Field(default=200, ge=72, le=600)
    emit_page_breaks: bool = True
    detect_tables: bool = True


class ParsedDocument(ContractModel):
    """Normalized parse result for exactly one source document."""

    document: DocumentRecord
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    elements: tuple[DocumentElement, ...]
    used_ocr: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class ParseFailure(ContractModel):
    """Typed per-file batch failure evidence."""

    document_id: str = Field(min_length=8)
    relative_path: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class BatchParseResult(ContractModel):
    """Batch output that preserves successes even when individual files fail."""

    successes: tuple[ParsedDocument, ...] = ()
    failures: tuple[ParseFailure, ...] = ()

    def exceeds_failure_policy(self, *, max_failures: int) -> bool:
        """Return whether the collected failures exceed an explicit policy."""
        if max_failures < 0:
            raise ValueError("max_failures must be non-negative")
        return len(self.failures) > max_failures
