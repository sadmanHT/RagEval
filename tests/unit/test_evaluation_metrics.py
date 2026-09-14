from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from rageval.core.errors import EvaluationError
from rageval.evaluation.judges import ScriptedJudge
from rageval.evaluation.metrics import (
    RagasMetricAdapter,
    answer_relevancy_score,
    classify_hallucination,
    context_precision,
    context_recall,
    faithfulness_score,
)
from rageval.evaluation.models import HallucinationSummary, JudgeResponse, JudgeVerdict
from rageval.models import Citation, GroundedAnswer


def _judge_response(score: float, verdict: JudgeVerdict) -> JudgeResponse:
    return JudgeResponse(
        score=score,
        verdict=verdict,
        rationale="fixture",
        evidence_chunk_ids=("chk_support_0001",),
        provider="scripted-fake",
        model="scripted-v1",
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )


def _answer(*, insufficient: bool = False) -> GroundedAnswer:
    return GroundedAnswer(
        question="What happened?",
        answer=("Context is insufficient." if insufficient else "Revenue rose. Margin improved."),
        citations=(
            []
            if insufficient
            else [
                Citation(chunk_id="chk_support_0001", claim="Revenue rose."),
                Citation(chunk_id="chk_support_0001", claim="Margin improved."),
            ]
        ),
        cited_chunk_ids=[] if insufficient else ["chk_support_0001"],
        insufficient_context=insufficient,
        refusal_reason="fixture refusal" if insufficient else None,
        provider="fixture",
        model="fixture-v1",
        latency_ms=1.0,
    )


def test_context_precision_deduplicates_retrieved_ids() -> None:
    assert (
        context_precision(
            ["chunk_a", "chunk_a", "chunk_b"],
            ["chunk_a"],
        )
        == 0.5
    )


def test_context_recall_handles_empty_context_and_no_required_support() -> None:
    assert context_recall([], ["chunk_a"]) == 0.0
    assert context_recall([], []) == 1.0
    assert context_precision([], []) == 1.0


@pytest.mark.asyncio
async def test_faithfulness_averages_partial_support() -> None:
    judge = ScriptedJudge(
        [
            _judge_response(1.0, JudgeVerdict.SUPPORTED),
            _judge_response(0.5, JudgeVerdict.PARTIAL),
        ]
    )
    score, outputs = await faithfulness_score(
        question="What happened?",
        reference_answer="Revenue rose and margin improved.",
        answer=_answer(),
        context_by_chunk_id={"chk_support_0001": "Revenue rose. Margin changed."},
        judge=judge,
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )
    assert score == 0.75
    assert [item.score for item in outputs] == [1.0, 0.5]


@pytest.mark.asyncio
async def test_refusal_with_no_claims_is_faithful() -> None:
    judge = ScriptedJudge([])
    score, outputs = await faithfulness_score(
        question="Unsupported?",
        reference_answer="No supported answer.",
        answer=_answer(insufficient=True),
        context_by_chunk_id={},
        judge=judge,
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )
    assert score == 1.0
    assert outputs == ()


@pytest.mark.asyncio
async def test_answer_relevancy_uses_structured_judge() -> None:
    judge = ScriptedJudge([_judge_response(0.25, JudgeVerdict.PARTIALLY_RELEVANT)])
    score, output = await answer_relevancy_score(
        question="What happened?",
        reference_answer="Revenue rose.",
        answer=_answer(),
        judge=judge,
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )
    assert score == 0.25
    assert output is not None
    assert output.verdict is JudgeVerdict.PARTIALLY_RELEVANT


@pytest.mark.asyncio
async def test_empty_non_refusal_answer_scores_zero_without_judge_calls() -> None:
    answer = GroundedAnswer(
        question="What happened?",
        answer=" ",
        provider="fixture",
        model="fixture-v1",
        latency_ms=1.0,
    )
    judge = ScriptedJudge([])
    faithfulness, outputs = await faithfulness_score(
        question=answer.question,
        reference_answer="A factual answer.",
        answer=answer,
        context_by_chunk_id={},
        judge=judge,
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )
    relevancy, relevancy_output = await answer_relevancy_score(
        question=answer.question,
        reference_answer="A factual answer.",
        answer=answer,
        judge=judge,
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )
    assert faithfulness == 0.0
    assert outputs == ()
    assert relevancy == 0.0
    assert relevancy_output is None


def test_hallucination_threshold_is_strictly_less_than_point_eight() -> None:
    assert not classify_hallucination(0.8)
    assert classify_hallucination(0.799999)


def test_hallucination_summary_rejects_inconsistent_rate() -> None:
    with pytest.raises(PydanticValidationError, match="flagged_count / total_count"):
        HallucinationSummary(
            threshold=0.8,
            flagged_count=1,
            total_count=3,
            rate=0.5,
        )


@pytest.mark.asyncio
async def test_ragas_adapter_validates_external_score_range() -> None:
    async def scorer(payload: dict[str, object]) -> float:
        assert payload["question"] == "fixture"
        return 0.75

    adapter = RagasMetricAdapter(
        metric_name="faithfulness",
        ragas_version="fixture-ragas-version",
        scorer=scorer,
    )
    assert await adapter.score({"question": "fixture"}) == 0.75

    async def invalid_scorer(payload: dict[str, object]) -> float:
        del payload
        return 1.2

    invalid = RagasMetricAdapter(
        metric_name="faithfulness",
        ragas_version="fixture-ragas-version",
        scorer=invalid_scorer,
    )
    with pytest.raises(EvaluationError, match="out-of-range"):
        await invalid.score({})
