"""Held-out evaluation loading, governance validation, review helpers, and fingerprints."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from rageval.core.errors import DataLeakageError, ValidationError
from rageval.corpus.manifest import assert_no_split_leakage
from rageval.corpus.models import CorpusManifest, DatasetSplit, EvaluationDatasetRecord


def fingerprint_evaluation_records(records: Sequence[EvaluationDatasetRecord]) -> str:
    """Fingerprint reviewed evaluation data independently of file/list ordering."""

    keyed: list[tuple[str, dict[str, object]]] = []
    for record in records:
        keyed.append(
            (
                record.example.example_id,
                {
                    "example": record.example.model_dump(mode="json"),
                    "split": record.split.value,
                    "supporting_document_ids": sorted(record.supporting_document_ids),
                    "corpus_fingerprint": record.corpus_fingerprint,
                },
            )
        )
    canonical = [payload for _, payload in sorted(keyed, key=lambda item: item[0])]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_evaluation_records(
    records: Sequence[EvaluationDatasetRecord],
    *,
    manifest: CorpusManifest | None = None,
) -> str:
    """Validate duplicate identity, held-out provenance, and optional corpus leakage boundaries."""

    if not records:
        raise ValidationError("evaluation dataset must contain at least one record")

    example_ids = [record.example.example_id for record in records]
    if len(set(example_ids)) != len(example_ids):
        raise ValidationError("evaluation dataset contains duplicate example IDs")

    for record in records:
        example = record.example
        if len(set(example.supporting_document_ids)) != len(example.supporting_document_ids):
            raise ValidationError(
                f"duplicate supporting document IDs in example {example.example_id}"
            )
        if len(set(example.supporting_chunk_ids)) != len(example.supporting_chunk_ids):
            raise ValidationError(f"duplicate supporting chunk IDs in example {example.example_id}")
        if example.supporting_document_ids and not set(example.supporting_document_ids).issubset(
            set(record.supporting_document_ids)
        ):
            raise ValidationError(
                f"example {example.example_id} supporting_document_ids must be represented "
                "by the enclosing evaluation record"
            )

    if manifest is not None:
        assert_no_split_leakage(list(manifest.documents))
        documents = {document.record.document_id: document for document in manifest.documents}
        for record in records:
            if record.corpus_fingerprint != manifest.fingerprint:
                raise DataLeakageError(
                    "evaluation record corpus fingerprint does not match validated manifest: "
                    f"example={record.example.example_id}"
                )
            for document_id in record.supporting_document_ids:
                document = documents.get(document_id)
                if document is None:
                    raise DataLeakageError(
                        f"evaluation example {record.example.example_id} references unknown "
                        f"document {document_id}"
                    )
                if document.split is not DatasetSplit.EVALUATION:
                    raise DataLeakageError(
                        f"evaluation example {record.example.example_id} references development "
                        f"document {document_id}"
                    )

    return fingerprint_evaluation_records(records)


def load_evaluation_jsonl(
    path: Path,
    *,
    manifest: CorpusManifest | None = None,
) -> tuple[EvaluationDatasetRecord, ...]:
    """Load strict JSONL records and optionally validate them against a corpus manifest."""

    records: list[EvaluationDatasetRecord] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    records.append(EvaluationDatasetRecord.model_validate_json(line))
                except PydanticValidationError as exc:
                    raise ValidationError(
                        f"invalid evaluation record at {path}:{line_number}: {exc}"
                    ) from exc
    except OSError as exc:
        raise ValidationError(f"cannot read evaluation dataset {path}: {exc}") from exc

    validate_evaluation_records(records, manifest=manifest)
    return tuple(records)


def write_evaluation_jsonl(records: Sequence[EvaluationDatasetRecord], path: Path) -> None:
    """Write stable example-ID ordering after validating the record set."""

    validate_evaluation_records(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda record: record.example.example_id)
    payload = "\n".join(record.model_dump_json() for record in ordered) + "\n"
    path.write_text(payload, encoding="utf-8")


def export_review_csv(records: Sequence[EvaluationDatasetRecord], path: Path) -> None:
    """Export concise human-review fields without mutating the canonical JSONL dataset."""

    validate_evaluation_records(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "example_id",
        "domain",
        "question",
        "reference_answer",
        "supporting_document_ids",
        "supporting_chunk_ids",
        "tags",
        "table_parsing_required",
        "reviewer_status",
        "reviewer",
    ]
    try:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for record in sorted(records, key=lambda item: item.example.example_id):
                example = record.example
                writer.writerow(
                    {
                        "example_id": example.example_id,
                        "domain": example.domain.value,
                        "question": example.question,
                        "reference_answer": example.reference_answer,
                        "supporting_document_ids": "|".join(record.supporting_document_ids),
                        "supporting_chunk_ids": "|".join(example.supporting_chunk_ids),
                        "tags": "|".join(example.tags),
                        "table_parsing_required": str(example.table_parsing_required).lower(),
                        "reviewer_status": example.reviewer_status,
                        "reviewer": example.reviewer or "",
                    }
                )
    except OSError as exc:
        raise ValidationError(f"cannot write evaluation review CSV {path}: {exc}") from exc
