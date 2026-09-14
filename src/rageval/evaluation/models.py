"""Typed Phase 11 evaluation, judge, and aggregation contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from rageval.models.contracts import (
    ContractModel,
    EvaluationExample,
    EvaluationResult,
    GroundedAnswer,
)


class EvaluationMetricName(StrEnum):
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    HALLUCINATION = "hallucination"


class JudgeMetric(StrEnum):
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"


class JudgeVerdict(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    RELEVANT = "relevant"
    PARTIALLY_RELEVANT = "partially_relevant"
    IRRELEVANT = "irrelevant"


class JudgeRequest(ContractModel):
    """Auditable semantic-scoring request with no hidden reasoning fields."""

    schema_version: str = "1.0"
    metric: JudgeMetric
    question: str = Field(min_length=1)
    candidate_text: str
    reference_answer: str = ""
    context_by_chunk_id: dict[str, str] = Field(default_factory=dict)
    prompt_version: str = Field(default="phase11-judge-prompt-v1", min_length=1)
    rubric_version: str = Field(default="phase11-rubric-v1", min_length=1)


class JudgeResponse(ContractModel):
    """Structured judge verdict; rationale is concise evidence, not chain-of-thought."""

    schema_version: str = "1.0"
    score: float = Field(ge=0, le=1)
    verdict: JudgeVerdict
    rationale: str = Field(min_length=1, max_length=500)
    evidence_chunk_ids: tuple[str, ...] = ()
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)


class EvaluationObservation(ContractModel):
    """Runtime output and retrieved evidence associated with one held-out example."""

    example: EvaluationExample
    answer: GroundedAnswer
    retrieved_chunk_ids: tuple[str, ...] = ()
    context_by_chunk_id: dict[str, str] = Field(default_factory=dict)


class EvaluationEngineConfig(ContractModel):
    schema_version: str = "1.0"
    metric_version: str = "phase11-metrics-v1"
    hallucination_threshold: float = Field(default=0.8, gt=0, le=1)
    prompt_version: str = "phase11-judge-prompt-v1"
    rubric_version: str = "phase11-rubric-v1"


class ExampleEvaluationRecord(ContractModel):
    schema_version: str = "1.0"
    example_id: str = Field(min_length=8)
    results: tuple[EvaluationResult, ...]
    judge_outputs: tuple[JudgeResponse, ...] = ()
    hallucinated: bool


class MetricAggregate(ContractModel):
    metric: EvaluationMetricName
    count: int = Field(ge=0)
    mean_score: float = Field(ge=0, le=1)


class HallucinationSummary(ContractModel):
    """Response-level hallucination arithmetic persisted as count / N."""

    threshold: float = Field(gt=0, le=1)
    flagged_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_arithmetic(self) -> HallucinationSummary:
        if self.flagged_count > self.total_count:
            raise ValueError("flagged_count cannot exceed total_count")
        expected = 0.0 if self.total_count == 0 else self.flagged_count / self.total_count
        if abs(self.rate - expected) > 1e-12:
            raise ValueError(
                "hallucination rate must equal flagged_count / total_count "
                f"(expected {expected}, got {self.rate})"
            )
        return self


class EvaluationRun(ContractModel):
    schema_version: str = "1.0"
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge_provider: str = Field(min_length=1)
    judge_model: str = Field(min_length=1)
    records: tuple[ExampleEvaluationRecord, ...]
    aggregates: tuple[MetricAggregate, ...]
    hallucination: HallucinationSummary
    metadata: dict[str, object] = Field(default_factory=dict)
