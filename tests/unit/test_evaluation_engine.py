from __future__ import annotations

import pytest

from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation.engine import EvaluationEngine
from rageval.evaluation.judges import ScriptedJudge
from rageval.evaluation.models import (
    EvaluationMetricName,
    EvaluationObservation,
    JudgeResponse,
    JudgeVerdict,
)
from rageval.models import Citation, Domain, EvaluationExample, GroundedAnswer


def _judge_response(score: float, verdict: JudgeVerdict) -> JudgeResponse:
    return JudgeResponse(
        score=score,
        verdict=verdict,
        rationale="fixture",
        provider="scripted-fake",
        model="scripted-v1",
        prompt_version="phase11-judge-prompt-v1",
        rubric_version="phase11-rubric-v1",
    )


def _record(example_id: str, support: str) -> EvaluationDatasetRecord:
    return EvaluationDatasetRecord(
        example=EvaluationExample(
            example_id=example_id,
            question=f"Question for {example_id}?",
            reference_answer=f"Reference for {example_id}.",
            domain=Domain.RESEARCH,
            supporting_document_ids=["doc_eval_fixture"],
            supporting_chunk_ids=[support],
            reviewer_status="approved",
            reviewer="fixture-reviewer",
        ),
        supporting_document_ids=("doc_eval_fixture",),
        corpus_fingerprint="b" * 64,
    )


def _observation(
    record: EvaluationDatasetRecord,
    support: str,
    *,
    extra: bool,
) -> EvaluationObservation:
    retrieved = (support, "chk_distractor") if extra else (support,)
    return EvaluationObservation(
        example=record.example,
        answer=GroundedAnswer(
            question=record.example.question,
            answer=f"Answer for {record.example.example_id}.",
            citations=[Citation(chunk_id=support, claim="fixture claim")],
            cited_chunk_ids=[support],
            provider="fixture",
            model="fixture-v1",
            latency_ms=1.0,
        ),
        retrieved_chunk_ids=retrieved,
        context_by_chunk_id={support: "fixture claim"},
    )


@pytest.mark.asyncio
async def test_engine_returns_reproducible_per_example_and_aggregate_math() -> None:
    first = _record("eval_engine_0001", "chk_support_0001")
    second = _record("eval_engine_0002", "chk_support_0002")
    observations = [
        _observation(first, "chk_support_0001", extra=True),
        _observation(second, "chk_support_0002", extra=False),
    ]
    responses = [
        _judge_response(1.0, JudgeVerdict.SUPPORTED),
        _judge_response(0.5, JudgeVerdict.PARTIALLY_RELEVANT),
        _judge_response(0.5, JudgeVerdict.PARTIAL),
        _judge_response(1.0, JudgeVerdict.RELEVANT),
    ]
    run = await EvaluationEngine(judge=ScriptedJudge(responses)).evaluate(
        [first, second],
        observations,
    )

    by_metric = {aggregate.metric: aggregate for aggregate in run.aggregates}
    assert by_metric[EvaluationMetricName.CONTEXT_PRECISION].mean_score == 0.75
    assert by_metric[EvaluationMetricName.CONTEXT_RECALL].mean_score == 1.0
    assert by_metric[EvaluationMetricName.FAITHFULNESS].mean_score == 0.75
    assert by_metric[EvaluationMetricName.ANSWER_RELEVANCY].mean_score == 0.75
    assert run.hallucination.flagged_count == 1
    assert run.hallucination.total_count == 2
    assert run.hallucination.rate == 0.5
    assert all(
        result.dataset_fingerprint == run.dataset_fingerprint
        for record in run.records
        for result in record.results
    )
    assert all(
        result.run_fingerprint == run.run_fingerprint
        for record in run.records
        for result in record.results
    )


@pytest.mark.asyncio
async def test_run_fingerprint_is_input_order_independent() -> None:
    first = _record("eval_engine_0001", "chk_support_0001")
    second = _record("eval_engine_0002", "chk_support_0002")
    first_observation = _observation(first, "chk_support_0001", extra=False)
    second_observation = _observation(second, "chk_support_0002", extra=False)
    responses = [
        _judge_response(1.0, JudgeVerdict.SUPPORTED),
        _judge_response(1.0, JudgeVerdict.RELEVANT),
        _judge_response(1.0, JudgeVerdict.SUPPORTED),
        _judge_response(1.0, JudgeVerdict.RELEVANT),
    ]
    forward = await EvaluationEngine(judge=ScriptedJudge(responses)).evaluate(
        [first, second],
        [first_observation, second_observation],
    )
    reverse = await EvaluationEngine(judge=ScriptedJudge(responses)).evaluate(
        [second, first],
        [second_observation, first_observation],
    )
    assert forward.dataset_fingerprint == reverse.dataset_fingerprint
    assert forward.run_fingerprint == reverse.run_fingerprint
