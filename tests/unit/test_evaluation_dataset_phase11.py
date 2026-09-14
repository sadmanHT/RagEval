from __future__ import annotations

from pathlib import Path

import pytest

from rageval.core.errors import DataLeakageError, ValidationError
from rageval.corpus.manifest import fingerprint_documents
from rageval.corpus.models import (
    CorpusDocument,
    CorpusManifest,
    DatasetSplit,
    EvaluationDatasetRecord,
)
from rageval.evaluation.dataset import (
    export_review_csv,
    fingerprint_evaluation_records,
    load_evaluation_jsonl,
    validate_evaluation_records,
    write_evaluation_jsonl,
)
from rageval.models import DocumentRecord, Domain, EvaluationExample, SourceType


def _document(document_id: str, split: DatasetSplit, checksum_char: str) -> CorpusDocument:
    return CorpusDocument(
        record=DocumentRecord(
            document_id=document_id,
            source_uri=f"file:///{split.value}/research/{document_id}.html",
            source_type=SourceType.HTML,
            domain=Domain.RESEARCH,
            checksum_sha256=checksum_char * 64,
        ),
        relative_path=f"{split.value}/research/{document_id}.html",
        logical_title=document_id,
        split=split,
        size_bytes=10,
    )


def _manifest() -> CorpusManifest:
    development = _document("doc_development_01", DatasetSplit.DEVELOPMENT, "1")
    evaluation = _document("doc_evaluation_001", DatasetSplit.EVALUATION, "2")
    documents = (development, evaluation)
    return CorpusManifest(
        root_hint="fixture",
        documents=documents,
        fingerprint=fingerprint_documents(list(documents)),
    )


def _record(
    example_id: str,
    document_id: str,
    corpus_fingerprint: str,
) -> EvaluationDatasetRecord:
    return EvaluationDatasetRecord(
        example=EvaluationExample(
            example_id=example_id,
            question="What method is described?",
            reference_answer="The fixture describes retrieval.",
            domain=Domain.RESEARCH,
            supporting_document_ids=[document_id],
            supporting_chunk_ids=["chk_fixture_0001"],
            tags=["research", "fixture"],
            provenance={"source": "unit-test"},
            reviewer_status="approved",
            reviewer="reviewer",
        ),
        supporting_document_ids=(document_id,),
        corpus_fingerprint=corpus_fingerprint,
    )


def test_phase11_example_fields_round_trip() -> None:
    record = _record("eval_phase11_0001", "doc_evaluation_001", "a" * 64)
    payload = record.model_dump(mode="json")
    assert payload["example"]["schema_version"] == "2.0"
    assert payload["example"]["split"] == "evaluation"
    assert payload["example"]["reviewer_status"] == "approved"
    assert payload["example"]["supporting_chunk_ids"] == ["chk_fixture_0001"]


def test_dataset_jsonl_round_trip_is_stable(tmp_path: Path) -> None:
    first = _record("eval_phase11_0002", "doc_evaluation_001", "a" * 64)
    second = _record("eval_phase11_0001", "doc_evaluation_001", "a" * 64)
    path = tmp_path / "dataset.jsonl"

    write_evaluation_jsonl([first, second], path)
    loaded = load_evaluation_jsonl(path)

    assert [item.example.example_id for item in loaded] == [
        "eval_phase11_0001",
        "eval_phase11_0002",
    ]
    assert fingerprint_evaluation_records(loaded) == fingerprint_evaluation_records(
        [second, first]
    )


def test_duplicate_example_ids_are_rejected() -> None:
    record = _record("eval_phase11_0001", "doc_evaluation_001", "a" * 64)
    with pytest.raises(ValidationError, match="duplicate example IDs"):
        validate_evaluation_records([record, record])


def test_manifest_validation_rejects_development_document_reference() -> None:
    manifest = _manifest()
    record = _record(
        "eval_phase11_0003",
        "doc_development_01",
        manifest.fingerprint,
    )
    with pytest.raises(DataLeakageError, match="references development"):
        validate_evaluation_records([record], manifest=manifest)


def test_manifest_validation_rejects_wrong_corpus_fingerprint() -> None:
    manifest = _manifest()
    record = _record("eval_phase11_0004", "doc_evaluation_001", "f" * 64)
    with pytest.raises(DataLeakageError, match="fingerprint"):
        validate_evaluation_records([record], manifest=manifest)


def test_review_csv_exports_human_review_fields(tmp_path: Path) -> None:
    record = _record("eval_phase11_0005", "doc_evaluation_001", "a" * 64)
    output = tmp_path / "review.csv"
    export_review_csv([record], output)
    text = output.read_text(encoding="utf-8")
    assert "reviewer_status" in text
    assert "approved" in text
    assert "chk_fixture_0001" in text
