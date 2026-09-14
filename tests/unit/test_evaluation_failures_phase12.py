from __future__ import annotations

from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation import (
    AblationConfiguration,
    ChunkingStrategy,
    EvaluationObservation,
    ExampleEvaluationRecord,
    FailureCategory,
    RetrievalPipeline,
    classify_failure,
)
from rageval.models import Citation, Domain, EvaluationExample, EvaluationResult, GroundedAnswer


def _dataset_record(*, all_signals: bool = False) -> EvaluationDatasetRecord:
    tags = ["vocabulary_mismatch", "long_range_reference"] if all_signals else []
    metadata = {"reranker_error": True} if all_signals else {}
    example = EvaluationExample(
        example_id="eval_failure_001",
        question="What is the supported fact?",
        reference_answer="The supported fact is three.",
        domain=Domain.LEGAL,
        supporting_document_ids=["doc_failure_001"],
        supporting_chunk_ids=["chk_failure_001"],
        tags=tags,
        table_parsing_required=all_signals,
        reviewer_status="approved",
        reviewer="phase12-test",
        metadata=metadata,
    )
    return EvaluationDatasetRecord(
        example=example,
        supporting_document_ids=("doc_failure_001",),
        corpus_fingerprint="c" * 64,
    )


def _observation(
    record: EvaluationDatasetRecord,
    *,
    valid_citation: bool,
) -> EvaluationObservation:
    citations = []
    cited_chunk_ids: list[str] = []
    context = {"chk_failure_001": record.example.reference_answer}
    if valid_citation:
        citations = [Citation(chunk_id="chk_failure_001", claim=record.example.reference_answer)]
        cited_chunk_ids = ["chk_failure_001"]
    return EvaluationObservation(
        example=record.example,
        answer=GroundedAnswer(
            question=record.example.question,
            answer=record.example.reference_answer,
            citations=citations,
            cited_chunk_ids=cited_chunk_ids,
            provider="phase12-test",
            model="fixture-v1",
            latency_ms=1.0,
        ),
        retrieved_chunk_ids=("chk_failure_001",),
        context_by_chunk_id=context,
    )


def _evaluated(
    *,
    precision: float,
    recall: float,
    faithfulness: float,
    relevancy: float,
    hallucinated: bool,
) -> ExampleEvaluationRecord:
    values = {
        "context_precision": precision,
        "context_recall": recall,
        "faithfulness": faithfulness,
        "answer_relevancy": relevancy,
        "hallucination": 1.0 if hallucinated else 0.0,
    }
    return ExampleEvaluationRecord(
        example_id="eval_failure_001",
        results=tuple(
            EvaluationResult(
                example_id="eval_failure_001",
                metric=metric,
                score=score,
                evaluator="phase12-test",
            )
            for metric, score in values.items()
        ),
        hallucinated=hallucinated,
    )


def _config() -> AblationConfiguration:
    return AblationConfiguration(
        config_id="taxonomy-fixture",
        retrieval_pipeline=RetrievalPipeline.HYBRID_RERANK,
        chunking_strategy=ChunkingStrategy.TABLE_AWARE,
    )


def test_failure_taxonomy_classifies_named_observable_signals() -> None:
    record = _dataset_record(all_signals=True)
    failure = classify_failure(
        record,
        _observation(record, valid_citation=False),
        _evaluated(
            precision=0.0,
            recall=0.0,
            faithfulness=0.5,
            relevancy=0.5,
            hallucinated=True,
        ),
        _config(),
    )
    assert failure is not None
    assert set(failure.categories) == {
        FailureCategory.TABLE_FRAGMENTATION,
        FailureCategory.VOCABULARY_MISMATCH,
        FailureCategory.LONG_RANGE_REFERENCE,
        FailureCategory.RETRIEVAL_MISS,
        FailureCategory.RERANKER_ERROR,
        FailureCategory.CITATION_FAILURE,
        FailureCategory.GENERATION_UNSUPPORTED_CLAIM,
    }


def test_failure_taxonomy_uses_unknown_when_metrics_degrade_without_cause() -> None:
    record = _dataset_record()
    failure = classify_failure(
        record,
        _observation(record, valid_citation=True),
        _evaluated(
            precision=0.5,
            recall=1.0,
            faithfulness=1.0,
            relevancy=1.0,
            hallucinated=False,
        ),
        _config(),
    )
    assert failure is not None
    assert failure.categories == (FailureCategory.UNKNOWN,)


def test_failure_taxonomy_returns_none_for_perfect_record() -> None:
    record = _dataset_record()
    failure = classify_failure(
        record,
        _observation(record, valid_citation=True),
        _evaluated(
            precision=1.0,
            recall=1.0,
            faithfulness=1.0,
            relevancy=1.0,
            hallucinated=False,
        ),
        _config(),
    )
    assert failure is None
