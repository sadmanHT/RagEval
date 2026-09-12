from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from rageval.corpus.models import DatasetSplit, EvaluationDatasetRecord
from rageval.evaluation.dataset import fingerprint_evaluation_records
from rageval.models import Domain, EvaluationExample


def _record(example_id: str) -> EvaluationDatasetRecord:
    return EvaluationDatasetRecord(
        example=EvaluationExample(
            example_id=example_id,
            question="What is stated?",
            reference_answer="The fixture states the answer.",
            domain=Domain.RESEARCH,
        ),
        supporting_document_ids=("doc_12345678",),
        corpus_fingerprint="f" * 64,
    )


def test_evaluation_fingerprint_is_order_independent() -> None:
    first = _record("eval_00000001")
    second = _record("eval_00000002")
    assert fingerprint_evaluation_records([first, second]) == fingerprint_evaluation_records(
        [second, first]
    )


def test_evaluation_record_cannot_be_development_split() -> None:
    with pytest.raises(PydanticValidationError, match="evaluation split"):
        EvaluationDatasetRecord(
            example=EvaluationExample(
                example_id="eval_00000003",
                question="q",
                reference_answer="a",
                domain=Domain.LEGAL,
            ),
            split=DatasetSplit.DEVELOPMENT,
            supporting_document_ids=("doc_12345678",),
            corpus_fingerprint="f" * 64,
        )
