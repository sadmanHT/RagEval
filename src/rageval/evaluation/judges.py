"""Provider-abstracted structured judge contracts and deterministic test judges."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Protocol

from pydantic import ValidationError as PydanticValidationError

from rageval.core.errors import EvaluationError
from rageval.evaluation.models import (
    JudgeMetric,
    JudgeRequest,
    JudgeResponse,
    JudgeVerdict,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class JudgeProvider(Protocol):
    """Semantic evaluation boundary used by faithfulness/relevancy metrics."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def judge(self, request: JudgeRequest) -> JudgeResponse: ...


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


class DeterministicRuleJudge:
    """Credential-free lexical judge for mechanics; not a semantic-quality benchmark."""

    name = "deterministic-rule"
    model = "lexical-overlap-v1"

    async def judge(self, request: JudgeRequest) -> JudgeResponse:
        if request.metric is JudgeMetric.FAITHFULNESS:
            return self._faithfulness(request)
        return self._relevancy(request)

    def _faithfulness(self, request: JudgeRequest) -> JudgeResponse:
        claim = _normalized(request.candidate_text)
        best_id: str | None = None
        best_overlap = 0.0
        claim_tokens = _tokens(claim)

        for chunk_id, text in sorted(request.context_by_chunk_id.items()):
            normalized_context = _normalized(text)
            if claim and claim in normalized_context:
                return JudgeResponse(
                    score=1.0,
                    verdict=JudgeVerdict.SUPPORTED,
                    rationale="claim text is directly present in supplied context",
                    evidence_chunk_ids=(chunk_id,),
                    provider=self.name,
                    model=self.model,
                    prompt_version=request.prompt_version,
                    rubric_version=request.rubric_version,
                )
            if not claim_tokens:
                continue
            overlap = len(claim_tokens & _tokens(text)) / len(claim_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_id = chunk_id

        if best_overlap >= 0.5:
            return JudgeResponse(
                score=0.5,
                verdict=JudgeVerdict.PARTIAL,
                rationale="claim has substantial lexical support but is not directly present",
                evidence_chunk_ids=(best_id,) if best_id else (),
                provider=self.name,
                model=self.model,
                prompt_version=request.prompt_version,
                rubric_version=request.rubric_version,
            )
        return JudgeResponse(
            score=0.0,
            verdict=JudgeVerdict.UNSUPPORTED,
            rationale="claim lacks sufficient support in supplied context",
            evidence_chunk_ids=(best_id,) if best_id else (),
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            rubric_version=request.rubric_version,
        )

    def _relevancy(self, request: JudgeRequest) -> JudgeResponse:
        answer_tokens = _tokens(request.candidate_text)
        target_tokens = _tokens(request.question) | _tokens(request.reference_answer)
        if not answer_tokens or not target_tokens:
            score = 0.0
        else:
            score = len(answer_tokens & target_tokens) / len(target_tokens)
        if score >= 0.6:
            verdict = JudgeVerdict.RELEVANT
        elif score >= 0.2:
            verdict = JudgeVerdict.PARTIALLY_RELEVANT
        else:
            verdict = JudgeVerdict.IRRELEVANT
        return JudgeResponse(
            score=score,
            verdict=verdict,
            rationale="score is deterministic lexical overlap with question/reference terms",
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            rubric_version=request.rubric_version,
        )


class ScriptedJudge:
    """Deterministic ordered fake used for exact arithmetic tests."""

    name = "scripted-fake"
    model = "scripted-v1"

    def __init__(self, responses: Sequence[JudgeResponse]) -> None:
        self._responses = list(responses)
        self._offset = 0

    async def judge(self, request: JudgeRequest) -> JudgeResponse:
        del request
        if self._offset >= len(self._responses):
            raise EvaluationError("scripted judge exhausted")
        response = self._responses[self._offset]
        self._offset += 1
        return response


def parse_judge_response(raw_json: str) -> JudgeResponse:
    """Parse strict structured judge output and reject hidden/unexpected fields."""

    try:
        payload = json.loads(raw_json)
        return JudgeResponse.model_validate(payload)
    except (json.JSONDecodeError, PydanticValidationError, TypeError) as exc:
        raise EvaluationError(f"invalid structured judge output: {exc}") from exc
