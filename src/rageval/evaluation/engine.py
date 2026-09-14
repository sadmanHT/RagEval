"""Reproducible Phase 11 per-example evaluation and aggregate arithmetic."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from rageval.core.errors import EvaluationError
from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation.dataset import fingerprint_evaluation_records
from rageval.evaluation.judges import JudgeProvider
from rageval.evaluation.metrics import (
    answer_relevancy_score,
    classify_hallucination,
    context_precision,
    context_recall,
    faithfulness_score,
)
from rageval.evaluation.models import (
    EvaluationEngineConfig,
    EvaluationMetricName,
    EvaluationObservation,
    EvaluationRun,
    ExampleEvaluationRecord,
    HallucinationSummary,
    MetricAggregate,
)
from rageval.models import EvaluationResult


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_engine_config(config: EvaluationEngineConfig) -> str:
    return _sha256_json(config.model_dump(mode="json"))


def fingerprint_run_inputs(
    observations: Sequence[EvaluationObservation],
    *,
    dataset_fingerprint: str,
    config_fingerprint: str,
    judge_provider: str,
    judge_model: str,
) -> str:
    payload = {
        "dataset_fingerprint": dataset_fingerprint,
        "config_fingerprint": config_fingerprint,
        "judge_provider": judge_provider,
        "judge_model": judge_model,
        "observations": [
            observation.model_dump(mode="json")
            for observation in sorted(
                observations,
                key=lambda item: item.example.example_id,
            )
        ],
    }
    return _sha256_json(payload)


class EvaluationEngine:
    """Compute deterministic retrieval arithmetic plus provider-abstracted semantic metrics."""

    def __init__(
        self,
        *,
        judge: JudgeProvider,
        config: EvaluationEngineConfig | None = None,
    ) -> None:
        self.judge = judge
        self.config = config or EvaluationEngineConfig()

    async def evaluate(
        self,
        records: Sequence[EvaluationDatasetRecord],
        observations: Sequence[EvaluationObservation],
    ) -> EvaluationRun:
        if not records:
            raise EvaluationError("evaluation requires at least one dataset record")
        record_by_id = {record.example.example_id: record for record in records}
        if len(record_by_id) != len(records):
            raise EvaluationError("evaluation dataset contains duplicate example IDs")

        observation_by_id = {item.example.example_id: item for item in observations}
        if len(observation_by_id) != len(observations):
            raise EvaluationError("evaluation observations contain duplicate example IDs")
        if set(record_by_id) != set(observation_by_id):
            missing = sorted(set(record_by_id) - set(observation_by_id))
            extra = sorted(set(observation_by_id) - set(record_by_id))
            raise EvaluationError(
                f"observation IDs must exactly match dataset IDs; missing={missing} extra={extra}"
            )

        for example_id, observation in observation_by_id.items():
            if observation.example != record_by_id[example_id].example:
                raise EvaluationError(
                    f"observation example payload differs from dataset record for {example_id}"
                )

        dataset_fingerprint = fingerprint_evaluation_records(records)
        config_fingerprint = fingerprint_engine_config(self.config)
        run_fingerprint = fingerprint_run_inputs(
            observations,
            dataset_fingerprint=dataset_fingerprint,
            config_fingerprint=config_fingerprint,
            judge_provider=self.judge.name,
            judge_model=self.judge.model,
        )

        example_records: list[ExampleEvaluationRecord] = []
        aggregate_values: dict[EvaluationMetricName, list[float]] = {
            EvaluationMetricName.CONTEXT_PRECISION: [],
            EvaluationMetricName.CONTEXT_RECALL: [],
            EvaluationMetricName.FAITHFULNESS: [],
            EvaluationMetricName.ANSWER_RELEVANCY: [],
        }
        hallucination_flags: list[bool] = []

        for example_id in sorted(record_by_id):
            observation = observation_by_id[example_id]
            example = observation.example
            precision = context_precision(
                observation.retrieved_chunk_ids,
                example.supporting_chunk_ids,
            )
            recall = context_recall(
                observation.retrieved_chunk_ids,
                example.supporting_chunk_ids,
            )
            faithfulness, faith_outputs = await faithfulness_score(
                question=example.question,
                reference_answer=example.reference_answer,
                answer=observation.answer,
                context_by_chunk_id=observation.context_by_chunk_id,
                judge=self.judge,
                prompt_version=self.config.prompt_version,
                rubric_version=self.config.rubric_version,
            )
            relevancy, relevancy_output = await answer_relevancy_score(
                question=example.question,
                reference_answer=example.reference_answer,
                answer=observation.answer,
                judge=self.judge,
                prompt_version=self.config.prompt_version,
                rubric_version=self.config.rubric_version,
            )
            hallucinated = classify_hallucination(
                faithfulness,
                threshold=self.config.hallucination_threshold,
            )
            hallucination_flags.append(hallucinated)

            values = {
                EvaluationMetricName.CONTEXT_PRECISION: precision,
                EvaluationMetricName.CONTEXT_RECALL: recall,
                EvaluationMetricName.FAITHFULNESS: faithfulness,
                EvaluationMetricName.ANSWER_RELEVANCY: relevancy,
            }
            for metric, score in values.items():
                aggregate_values[metric].append(score)

            judge_outputs = list(faith_outputs)
            if relevancy_output is not None:
                judge_outputs.append(relevancy_output)

            metric_results = tuple(
                EvaluationResult(
                    example_id=example_id,
                    metric=metric.value,
                    score=score,
                    evaluator=(
                        self.judge.name
                        if metric
                        in {
                            EvaluationMetricName.FAITHFULNESS,
                            EvaluationMetricName.ANSWER_RELEVANCY,
                        }
                        else "deterministic-set-arithmetic"
                    ),
                    metric_version=self.config.metric_version,
                    dataset_fingerprint=dataset_fingerprint,
                    run_fingerprint=run_fingerprint,
                    metadata={
                        "config_fingerprint": config_fingerprint,
                        "prompt_version": self.config.prompt_version,
                        "rubric_version": self.config.rubric_version,
                    },
                )
                for metric, score in values.items()
            ) + (
                EvaluationResult(
                    example_id=example_id,
                    metric=EvaluationMetricName.HALLUCINATION.value,
                    score=1.0 if hallucinated else 0.0,
                    evaluator="faithfulness-threshold",
                    metric_version=self.config.metric_version,
                    dataset_fingerprint=dataset_fingerprint,
                    run_fingerprint=run_fingerprint,
                    metadata={
                        "threshold": self.config.hallucination_threshold,
                        "faithfulness": faithfulness,
                    },
                ),
            )

            example_records.append(
                ExampleEvaluationRecord(
                    example_id=example_id,
                    results=metric_results,
                    judge_outputs=tuple(judge_outputs),
                    hallucinated=hallucinated,
                )
            )

        aggregates = tuple(
            MetricAggregate(
                metric=metric,
                count=len(scores),
                mean_score=sum(scores) / len(scores) if scores else 0.0,
            )
            for metric, scores in aggregate_values.items()
        )
        flagged_count = sum(1 for flag in hallucination_flags if flag)
        hallucination = HallucinationSummary(
            threshold=self.config.hallucination_threshold,
            flagged_count=flagged_count,
            total_count=len(hallucination_flags),
            rate=flagged_count / len(hallucination_flags),
        )
        return EvaluationRun(
            dataset_fingerprint=dataset_fingerprint,
            config_fingerprint=config_fingerprint,
            run_fingerprint=run_fingerprint,
            judge_provider=self.judge.name,
            judge_model=self.judge.model,
            records=tuple(example_records),
            aggregates=aggregates,
            hallucination=hallucination,
            metadata={
                "metric_version": self.config.metric_version,
                "prompt_version": self.config.prompt_version,
                "rubric_version": self.config.rubric_version,
            },
        )
