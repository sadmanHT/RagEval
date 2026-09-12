"""Versioned corpus and evaluation-data contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from rageval.models.contracts import ContractModel, DocumentRecord, EvaluationExample


class DatasetSplit(StrEnum):
    """Leakage boundary for development/tuning versus held-out evaluation data."""

    DEVELOPMENT = "development"
    EVALUATION = "evaluation"


class SourceLocator(ContractModel):
    """Optional coordinates known before or alongside parsing."""

    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_hint: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> SourceLocator:
        if self.page_start is None and self.page_end is not None:
            raise ValueError("page_end requires page_start")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class CorpusDocument(ContractModel):
    """One source file plus governance metadata used before content parsing."""

    record: DocumentRecord
    relative_path: str = Field(min_length=1)
    logical_title: str = Field(min_length=1)
    split: DatasetSplit
    size_bytes: int = Field(ge=0)
    source_date: date | None = None
    parser_version: str = Field(default="unparsed", min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    security_tags: tuple[str, ...] = ()
    locator: SourceLocator | None = None


class DuplicateGroup(ContractModel):
    """Checksum-identical sources discovered inside a corpus."""

    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_ids: tuple[str, ...] = Field(min_length=2)
    relative_paths: tuple[str, ...] = Field(min_length=2)


class CorpusManifest(ContractModel):
    """Portable manifest whose fingerprint excludes scan-time metadata."""

    schema_version: str = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    root_hint: str = Field(min_length=1)
    documents: tuple[CorpusDocument, ...]
    duplicates: tuple[DuplicateGroup, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvaluationDatasetRecord(ContractModel):
    """Phase-2 wrapper binding an evaluation example to held-out documents."""

    example: EvaluationExample
    split: DatasetSplit = DatasetSplit.EVALUATION
    supporting_document_ids: tuple[str, ...] = Field(min_length=1)
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_evaluation_split(self) -> EvaluationDatasetRecord:
        if self.split is not DatasetSplit.EVALUATION:
            raise ValueError("evaluation records must use the evaluation split")
        return self
