from __future__ import annotations

from pathlib import Path

import pytest

from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation import (
    DeterministicRuleJudge,
    EvaluationEngine,
    EvaluationMetricName,
    EvaluationObservation,
    load_evaluation_jsonl,
)
from rageval.models import Citation, GroundedAnswer

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "evaluation" / "phase11_records.jsonl"
)


def _observations(
    records: tuple[EvaluationDatasetRecord, ...],
) -> list[EvaluationObservation]:
    by_id = {record.example.example_id: record for record in records}

    financial = by_id["eval_fixture_fin_001"]
    legal = by_id["eval_fixture_legal_01"]
    research = by_id["eval_fixture_research_01"]

    return [
        EvaluationObservation(
            example=financial.example,
            answer=GroundedAnswer(
                question=financial.example.question,
                answer="Example Corp reported revenue of $125 million in Q3 2026.",
                citations=[
                    Citation(
                        chunk_id="chk_fin_fixture_01",
                        claim="Example Corp reported revenue of $125 million in Q3 2026.",
                    )
                ],
                cited_chunk_ids=["chk_fin_fixture_01"],
                provider="fixture",
                model="fixture-v1",
                latency_ms=1.0,
            ),
            retrieved_chunk_ids=("chk_fin_fixture_01", "chk_distractor_01"),
            context_by_chunk_id={
                "chk_fin_fixture_01": ("Example Corp reported revenue of $125 million in Q3 2026."),
                "chk_distractor_01": "Unrelated fixture text.",
            },
        ),
        EvaluationObservation(
            example=legal.example,
            answer=GroundedAnswer(
                question=legal.example.question,
                answer=(
                    "Confidentiality obligations survive termination for three years. "
                    "Termination requires ten years of notice."
                ),
                citations=[
                    Citation(
                        chunk_id="chk_legal_fixture_01",
                        claim="Confidentiality obligations survive termination for three years.",
                    ),
                    Citation(
                        chunk_id="chk_legal_fixture_01",
                        claim="Termination requires ten years of notice.",
                    ),
                ],
                cited_chunk_ids=["chk_legal_fixture_01"],
                provider="fixture",
                model="fixture-v1",
                latency_ms=1.0,
            ),
            retrieved_chunk_ids=("chk_legal_fixture_01",),
            context_by_chunk_id={
                "chk_legal_fixture_01": (
                    "Confidentiality obligations survive termination for three years."
                )
            },
        ),
        EvaluationObservation(
            example=research.example,
            answer=GroundedAnswer(
                question=research.example.question,
                answer="The fixture research paper evaluated retrieval augmented generation.",
                citations=[
                    Citation(
                        chunk_id="chk_research_fixture_01",
                        claim=(
                            "The fixture research paper evaluated retrieval augmented generation."
                        ),
                    )
                ],
                cited_chunk_ids=["chk_research_fixture_01"],
                provider="fixture",
                model="fixture-v1",
                latency_ms=1.0,
            ),
            retrieved_chunk_ids=("chk_research_fixture_01",),
            context_by_chunk_id={
                "chk_research_fixture_01": (
                    "The fixture research paper evaluated retrieval augmented generation."
                )
            },
        ),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tiny_fixture_evaluation_is_reproducible_and_arithmetically_correct() -> None:
    records = load_evaluation_jsonl(FIXTURE_PATH)
    observations = _observations(records)
    first = await EvaluationEngine(judge=DeterministicRuleJudge()).evaluate(
        records,
        observations,
    )
    second = await EvaluationEngine(judge=DeterministicRuleJudge()).evaluate(
        records,
        list(reversed(observations)),
    )

    assert first.run_fingerprint == second.run_fingerprint
    aggregates = {item.metric: item.mean_score for item in first.aggregates}
    assert aggregates[EvaluationMetricName.CONTEXT_PRECISION] == pytest.approx(5 / 6)
    assert aggregates[EvaluationMetricName.CONTEXT_RECALL] == pytest.approx(5 / 6)
    assert aggregates[EvaluationMetricName.FAITHFULNESS] == pytest.approx(5 / 6)
    assert first.hallucination.flagged_count == 1
    assert first.hallucination.total_count == 3
    assert first.hallucination.rate == pytest.approx(1 / 3)
