"""Evaluation dataset, metrics, judge contracts, and reproducible run engine."""

from rageval.evaluation.dataset import (
    export_review_csv,
    fingerprint_evaluation_records,
    load_evaluation_jsonl,
    validate_evaluation_records,
    write_evaluation_jsonl,
)
from rageval.evaluation.engine import (
    EvaluationEngine,
    fingerprint_engine_config,
    fingerprint_run_inputs,
)
from rageval.evaluation.judges import (
    DeterministicRuleJudge,
    JudgeProvider,
    ScriptedJudge,
    parse_judge_response,
)
from rageval.evaluation.metrics import (
    RagasMetricAdapter,
    answer_relevancy_score,
    classify_hallucination,
    context_precision,
    context_recall,
    extract_claims,
    faithfulness_score,
)
from rageval.evaluation.models import (
    EvaluationEngineConfig,
    EvaluationMetricName,
    EvaluationObservation,
    EvaluationRun,
    ExampleEvaluationRecord,
    HallucinationSummary,
    JudgeMetric,
    JudgeRequest,
    JudgeResponse,
    JudgeVerdict,
    MetricAggregate,
)

__all__ = [
    "DeterministicRuleJudge",
    "EvaluationEngine",
    "EvaluationEngineConfig",
    "EvaluationMetricName",
    "EvaluationObservation",
    "EvaluationRun",
    "ExampleEvaluationRecord",
    "HallucinationSummary",
    "JudgeMetric",
    "JudgeProvider",
    "JudgeRequest",
    "JudgeResponse",
    "JudgeVerdict",
    "MetricAggregate",
    "RagasMetricAdapter",
    "ScriptedJudge",
    "answer_relevancy_score",
    "classify_hallucination",
    "context_precision",
    "context_recall",
    "export_review_csv",
    "extract_claims",
    "faithfulness_score",
    "fingerprint_engine_config",
    "fingerprint_evaluation_records",
    "fingerprint_run_inputs",
    "load_evaluation_jsonl",
    "parse_judge_response",
    "validate_evaluation_records",
    "write_evaluation_jsonl",
]
