"""Emit deterministic Phase 11 evaluation-fixture evidence as JSON."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation import (
    DeterministicRuleJudge,
    EvaluationEngine,
    EvaluationObservation,
    load_evaluation_jsonl,
)
from rageval.models import Citation, GroundedAnswer

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "evaluation" / "phase11_records.jsonl"


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
                "chk_fin_fixture_01": (
                    "Example Corp reported revenue of $125 million in Q3 2026."
                ),
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


async def _report() -> dict[str, object]:
    records = load_evaluation_jsonl(FIXTURE_PATH)
    run = await EvaluationEngine(judge=DeterministicRuleJudge()).evaluate(
        records,
        _observations(records),
    )
    aggregates = {item.metric.value: item.mean_score for item in run.aggregates}
    if run.hallucination.flagged_count != 1 or run.hallucination.total_count != 3:
        raise AssertionError("Phase 11 hallucination arithmetic fixture changed unexpectedly")
    if abs(run.hallucination.rate - (1 / 3)) > 1e-12:
        raise AssertionError("Phase 11 hallucination rate is not flagged_count / total_count")

    return {
        "schema_version": "1.0",
        "fixture_records": len(records),
        "target_dataset_supplied": False,
        "dataset_fingerprint": run.dataset_fingerprint,
        "config_fingerprint": run.config_fingerprint,
        "run_fingerprint": run.run_fingerprint,
        "judge": {
            "provider": run.judge_provider,
            "model": run.judge_model,
            "prompt_version": run.metadata["prompt_version"],
            "rubric_version": run.metadata["rubric_version"],
        },
        "aggregates": aggregates,
        "hallucination": run.hallucination.model_dump(mode="json"),
        "examples": [
            {
                "example_id": record.example_id,
                "hallucinated": record.hallucinated,
                "metrics": {result.metric: result.score for result in record.results},
            }
            for record in run.records
        ],
        "evidence_label": "deterministic-fixture-mechanics-only",
    }


def main() -> None:
    print(json.dumps(asyncio.run(_report()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
