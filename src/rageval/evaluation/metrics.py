"""Deterministic metric arithmetic and stable external-semantic adapters."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from rageval.core.errors import EvaluationError
from rageval.evaluation.judges import JudgeProvider
from rageval.evaluation.models import JudgeMetric, JudgeRequest, JudgeResponse
from rageval.models import GroundedAnswer

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _unique(values: Sequence[str]) -> set[str]:
    return {value for value in values if value}


def context_precision(
    retrieved_chunk_ids: Sequence[str],
    supporting_chunk_ids: Sequence[str],
) -> float:
    """Set precision over canonical chunk IDs; duplicate retrieved IDs do not inflate N."""

    retrieved = _unique(retrieved_chunk_ids)
    supporting = _unique(supporting_chunk_ids)
    if not retrieved:
        return 1.0 if not supporting else 0.0
    return len(retrieved & supporting) / len(retrieved)


def context_recall(
    retrieved_chunk_ids: Sequence[str],
    supporting_chunk_ids: Sequence[str],
) -> float:
    """Set recall over canonical chunk IDs; no required support is treated as fully recalled."""

    retrieved = _unique(retrieved_chunk_ids)
    supporting = _unique(supporting_chunk_ids)
    if not supporting:
        return 1.0
    return len(retrieved & supporting) / len(supporting)


def extract_claims(answer: GroundedAnswer) -> tuple[str, ...]:
    """Prefer explicit citation claims; otherwise split a non-refusal answer deterministically."""

    if answer.insufficient_context:
        return ()
    citation_claims = (
        citation.claim.strip()
        for citation in answer.citations
        if citation.claim.strip()
    )
    cited_claims = tuple(dict.fromkeys(citation_claims))
    if cited_claims:
        return cited_claims
    stripped = answer.answer.strip()
    if not stripped:
        return ()
    claims = tuple(
        dict.fromkeys(part.strip() for part in _SENTENCE_SPLIT_RE.split(stripped) if part.strip())
    )
    return claims


async def faithfulness_score(
    *,
    question: str,
    reference_answer: str,
    answer: GroundedAnswer,
    context_by_chunk_id: dict[str, str],
    judge: JudgeProvider,
    prompt_version: str,
    rubric_version: str,
) -> tuple[float, tuple[JudgeResponse, ...]]:
    """Average structured claim-support verdicts against only supplied context."""

    claims = extract_claims(answer)
    if not claims:
        return (1.0 if answer.insufficient_context else 0.0), ()

    outputs: list[JudgeResponse] = []
    for claim in claims:
        output = await judge.judge(
            JudgeRequest(
                metric=JudgeMetric.FAITHFULNESS,
                question=question,
                candidate_text=claim,
                reference_answer=reference_answer,
                context_by_chunk_id=context_by_chunk_id,
                prompt_version=prompt_version,
                rubric_version=rubric_version,
            )
        )
        outputs.append(output)
    return sum(output.score for output in outputs) / len(outputs), tuple(outputs)


async def answer_relevancy_score(
    *,
    question: str,
    reference_answer: str,
    answer: GroundedAnswer,
    judge: JudgeProvider,
    prompt_version: str,
    rubric_version: str,
) -> tuple[float, JudgeResponse | None]:
    """Judge whether the produced answer addresses the requested question/reference."""

    candidate = answer.answer.strip()
    if not candidate:
        return 0.0, None
    output = await judge.judge(
        JudgeRequest(
            metric=JudgeMetric.ANSWER_RELEVANCY,
            question=question,
            candidate_text=candidate,
            reference_answer=reference_answer,
            prompt_version=prompt_version,
            rubric_version=rubric_version,
        )
    )
    return output.score, output


def classify_hallucination(faithfulness: float, *, threshold: float = 0.8) -> bool:
    """Response-level hallucination definition used by RAG-Eval."""

    if not 0.0 <= faithfulness <= 1.0:
        raise EvaluationError("faithfulness must be within [0, 1]")
    if not 0.0 < threshold <= 1.0:
        raise EvaluationError("hallucination threshold must be within (0, 1]")
    return faithfulness < threshold


class RagasScorer(Protocol):
    """Narrow callable contract for an optional RAGAS-backed semantic metric."""

    def __call__(self, payload: dict[str, object]) -> Awaitable[float]: ...


class RagasMetricAdapter:
    """Stable RAG-Eval wrapper around an injected RAGAS scorer.

    The core package intentionally does not require RAGAS. A caller that enables a RAGAS
    tier supplies the concrete scorer and records its installed version here.
    """

    name = "ragas"

    def __init__(
        self,
        *,
        metric_name: str,
        ragas_version: str,
        scorer: Callable[[dict[str, object]], Awaitable[float]],
    ) -> None:
        if not metric_name:
            raise ValueError("metric_name is required")
        if not ragas_version:
            raise ValueError("ragas_version is required")
        self.metric_name = metric_name
        self.ragas_version = ragas_version
        self._scorer = scorer

    async def score(self, payload: dict[str, object]) -> float:
        score = float(await self._scorer(payload))
        if not 0.0 <= score <= 1.0:
            raise EvaluationError(
                f"RAGAS metric {self.metric_name!r} returned out-of-range score {score}"
            )
        return score
