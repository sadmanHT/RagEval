from __future__ import annotations

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from rageval.core.errors import EvaluationError
from rageval.evaluation.judges import (
    DeterministicRuleJudge,
    ScriptedJudge,
    parse_judge_response,
)
from rageval.evaluation.models import (
    JudgeMetric,
    JudgeRequest,
    JudgeResponse,
    JudgeVerdict,
)


def _response(score: float, verdict: JudgeVerdict) -> JudgeResponse:
    return JudgeResponse(
        score=score,
        verdict=verdict,
        rationale="fixture verdict",
        provider="scripted-fake",
        model="scripted-v1",
        prompt_version="prompt-v1",
        rubric_version="rubric-v1",
    )


@pytest.mark.asyncio
async def test_rule_judge_finds_direct_claim_support() -> None:
    judge = DeterministicRuleJudge()
    response = await judge.judge(
        JudgeRequest(
            metric=JudgeMetric.FAITHFULNESS,
            question="What was revenue?",
            candidate_text="Revenue was $125 million.",
            context_by_chunk_id={
                "chk_support_0001": "Example Corp reported: Revenue was $125 million."
            },
        )
    )
    assert response.score == 1.0
    assert response.verdict is JudgeVerdict.SUPPORTED
    assert response.evidence_chunk_ids == ("chk_support_0001",)


@pytest.mark.asyncio
async def test_scripted_judge_exhaustion_is_typed() -> None:
    judge = ScriptedJudge([_response(1.0, JudgeVerdict.SUPPORTED)])
    request = JudgeRequest(
        metric=JudgeMetric.ANSWER_RELEVANCY,
        question="q",
        candidate_text="a",
    )
    assert (await judge.judge(request)).score == 1.0
    with pytest.raises(EvaluationError, match="exhausted"):
        await judge.judge(request)


def test_structured_judge_output_parses_without_hidden_reasoning() -> None:
    raw = json.dumps(
        {
            "score": 1.0,
            "verdict": "supported",
            "rationale": "claim is directly stated",
            "evidence_chunk_ids": ["chk_support_0001"],
            "provider": "fixture",
            "model": "fixture-v1",
            "prompt_version": "prompt-v1",
            "rubric_version": "rubric-v1",
        }
    )
    parsed = parse_judge_response(raw)
    assert parsed.verdict is JudgeVerdict.SUPPORTED
    assert parsed.rationale == "claim is directly stated"


def test_structured_judge_output_rejects_chain_of_thought_field() -> None:
    raw = json.dumps(
        {
            "score": 1.0,
            "verdict": "supported",
            "rationale": "concise evidence",
            "reasoning": "private hidden reasoning should not be persisted",
            "provider": "fixture",
            "model": "fixture-v1",
            "prompt_version": "prompt-v1",
            "rubric_version": "rubric-v1",
        }
    )
    with pytest.raises(EvaluationError, match="invalid structured judge output"):
        parse_judge_response(raw)


def test_judge_response_score_range_is_strict() -> None:
    with pytest.raises(PydanticValidationError):
        _response(1.1, JudgeVerdict.SUPPORTED)
