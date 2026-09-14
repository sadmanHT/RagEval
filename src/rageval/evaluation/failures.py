"""Deterministic Phase 12 failure-taxonomy helpers."""

from __future__ import annotations

from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation.models import EvaluationObservation, ExampleEvaluationRecord
from rageval.evaluation.run_models import (
    AblationConfiguration,
    FailureAnalysisRecord,
    FailureCategory,
)


def _metric_scores(record: ExampleEvaluationRecord) -> dict[str, float]:
    return {result.metric: result.score for result in record.results}


def _has_tag(tags: set[str], *candidates: str) -> bool:
    return any(candidate in tags for candidate in candidates)


def classify_failure(
    dataset_record: EvaluationDatasetRecord,
    observation: EvaluationObservation,
    evaluation_record: ExampleEvaluationRecord,
    config: AblationConfiguration,
) -> FailureAnalysisRecord | None:
    """Classify observable failures without inventing hidden pipeline causes."""

    scores = _metric_scores(evaluation_record)
    recall = scores.get("context_recall", 1.0)
    faithfulness = scores.get("faithfulness", 1.0)
    relevancy = scores.get("answer_relevancy", 1.0)
    precision = scores.get("context_precision", 1.0)
    tags = {tag.lower().replace("-", "_") for tag in dataset_record.example.tags}

    categories: list[FailureCategory] = []
    details: list[str] = []

    def add(category: FailureCategory, detail: str) -> None:
        if category not in categories:
            categories.append(category)
            details.append(detail)

    if dataset_record.example.table_parsing_required and recall < 1.0:
        add(
            FailureCategory.TABLE_FRAGMENTATION,
            "table-required example lost one or more labeled supporting chunks",
        )
    if _has_tag(tags, "vocabulary_mismatch") and recall < 1.0:
        add(
            FailureCategory.VOCABULARY_MISMATCH,
            "curated vocabulary-mismatch example has incomplete context recall",
        )
    if _has_tag(tags, "long_range_reference", "long_range") and recall < 1.0:
        add(
            FailureCategory.LONG_RANGE_REFERENCE,
            "curated long-range-reference example has incomplete context recall",
        )
    if recall == 0.0:
        add(
            FailureCategory.RETRIEVAL_MISS,
            "none of the labeled supporting chunks were retrieved",
        )

    reranker_signal = bool(dataset_record.example.metadata.get("reranker_error"))
    reranker_signal = reranker_signal or _has_tag(tags, "reranker_error")
    if config.retrieval_pipeline.value == "hybrid_rerank" and reranker_signal:
        add(
            FailureCategory.RERANKER_ERROR,
            "example carries an explicit reranker-error signal under a reranked configuration",
        )

    answer = observation.answer
    cited_ids = set(answer.cited_chunk_ids)
    cited_ids.update(citation.chunk_id for citation in answer.citations)
    context_ids = set(observation.context_by_chunk_id)
    missing_citations = cited_ids - context_ids
    if not answer.insufficient_context and (not cited_ids or missing_citations):
        detail = "non-refusal answer has no citations"
        if missing_citations:
            detail = (
                "citations reference chunks outside supplied context: "
                f"{sorted(missing_citations)}"
            )
        add(FailureCategory.CITATION_FAILURE, detail)

    if evaluation_record.hallucinated:
        add(
            FailureCategory.GENERATION_UNSUPPORTED_CLAIM,
            f"faithfulness {faithfulness:.6f} is below the configured hallucination threshold",
        )

    degraded = any(score < 1.0 for score in (precision, recall, faithfulness, relevancy))
    if degraded and not categories:
        add(
            FailureCategory.UNKNOWN,
            "one or more metrics degraded without enough observable evidence for a named cause",
        )

    if not categories:
        return None
    return FailureAnalysisRecord(
        example_id=dataset_record.example.example_id,
        categories=tuple(categories),
        details=tuple(details),
    )
