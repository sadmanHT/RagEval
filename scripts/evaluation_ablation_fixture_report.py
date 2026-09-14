"""Run the deterministic Phase 12 comparative-evaluation fixture and emit JSON evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation import (
    AblationConfiguration,
    AsyncEvaluationRunner,
    ChunkingStrategy,
    DeterministicRuleJudge,
    EvaluationEngine,
    EvaluationMatrix,
    EvaluationObservation,
    RetrievalPipeline,
    aggregate_metric_slices,
    build_environment,
    load_evaluation_jsonl,
)
from rageval.models import Citation, GroundedAnswer
from rageval.testing.fakes import FakeExperimentTracker

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "evaluation" / "phase11_records.jsonl"
FIXTURE_INDEX_FINGERPRINT = hashlib.sha256(b"phase12-fixture-index-v1").hexdigest()

_SUPPORT_TEXT = {
    "chk_fin_fixture_01": "Example Corp reported revenue of $125 million in Q3 2026.",
    "chk_legal_fixture_01": "Confidentiality obligations survive termination for three years.",
    "chk_research_fixture_01": (
        "The fixture research paper evaluated retrieval augmented generation."
    ),
    "chk_research_fixture_02": "The experiment compared multiple retrieval configurations.",
}


class FixtureObservationProvider:
    name = "phase12-deterministic-fixture"

    async def observe(
        self,
        record: EvaluationDatasetRecord,
        config: AblationConfiguration,
    ) -> EvaluationObservation:
        await asyncio.sleep(0)
        example = record.example
        if example.example_id == "eval_fixture_fin_001":
            if config.chunking_strategy is ChunkingStrategy.FIXED_256:
                return EvaluationObservation(
                    example=example,
                    answer=GroundedAnswer(
                        question=example.question,
                        answer="Insufficient context.",
                        citations=[],
                        cited_chunk_ids=[],
                        insufficient_context=True,
                        refusal_reason="fixture retrieval miss",
                        provider=self.name,
                        model="fixture-v1",
                        latency_ms=1.0,
                    ),
                    retrieved_chunk_ids=("chk_distractor_fin",),
                    context_by_chunk_id={"chk_distractor_fin": "Unrelated financial text."},
                )
            return _supported_observation(
                record,
                support_ids=("chk_fin_fixture_01",),
                include_distractor=config.retrieval_pipeline is RetrievalPipeline.HYBRID_RRF,
            )

        if example.example_id == "eval_fixture_legal_01":
            if config.chunking_strategy is ChunkingStrategy.SEMANTIC:
                claim = "Termination requires ten years of notice."
                return EvaluationObservation(
                    example=example,
                    answer=GroundedAnswer(
                        question=example.question,
                        answer=f"{_SUPPORT_TEXT['chk_legal_fixture_01']} {claim}",
                        citations=[
                            Citation(
                                chunk_id="chk_legal_fixture_01",
                                claim=_SUPPORT_TEXT["chk_legal_fixture_01"],
                            ),
                            Citation(chunk_id="chk_legal_fixture_01", claim=claim),
                        ],
                        cited_chunk_ids=["chk_legal_fixture_01"],
                        provider=self.name,
                        model="fixture-v1",
                        latency_ms=1.0,
                    ),
                    retrieved_chunk_ids=("chk_legal_fixture_01",),
                    context_by_chunk_id={
                        "chk_legal_fixture_01": _SUPPORT_TEXT["chk_legal_fixture_01"]
                    },
                )
            return _supported_observation(
                record,
                support_ids=("chk_legal_fixture_01",),
                include_distractor=config.retrieval_pipeline is not RetrievalPipeline.HYBRID_RERANK,
            )

        support_ids = (
            ("chk_research_fixture_01",)
            if config.retrieval_pipeline is RetrievalPipeline.DENSE_ONLY
            else ("chk_research_fixture_01", "chk_research_fixture_02")
        )
        return _supported_observation(
            record,
            support_ids=support_ids,
            include_distractor=config.retrieval_pipeline is RetrievalPipeline.HYBRID_RRF,
        )


def _supported_observation(
    record: EvaluationDatasetRecord,
    *,
    support_ids: tuple[str, ...],
    include_distractor: bool,
) -> EvaluationObservation:
    example = record.example
    primary = support_ids[0]
    retrieved = list(support_ids)
    context = {chunk_id: _SUPPORT_TEXT[chunk_id] for chunk_id in support_ids}
    if include_distractor:
        distractor = f"chk_distractor_{example.domain.value}"
        retrieved.append(distractor)
        context[distractor] = "Unrelated deterministic fixture text."
    return EvaluationObservation(
        example=example,
        answer=GroundedAnswer(
            question=example.question,
            answer=example.reference_answer,
            citations=[Citation(chunk_id=primary, claim=example.reference_answer)],
            cited_chunk_ids=[primary],
            provider="phase12-deterministic-fixture",
            model="fixture-v1",
            latency_ms=1.0,
        ),
        retrieved_chunk_ids=tuple(retrieved),
        context_by_chunk_id=context,
    )


def _config(
    config_id: str,
    pipeline: RetrievalPipeline,
    chunking: ChunkingStrategy,
    *,
    query_expansion: bool = False,
    multi_hop: bool = False,
) -> AblationConfiguration:
    return AblationConfiguration(
        config_id=config_id,
        retrieval_pipeline=pipeline,
        chunking_strategy=chunking,
        query_expansion=query_expansion,
        multi_hop=multi_hop,
        provider_versions={
            "observation": "phase12-deterministic-fixture/fixture-v1",
            "judge": "deterministic-rule/lexical-overlap-v1",
        },
        prompt_versions={"judge": "phase11-judge-prompt-v1"},
        retrieval_params={"fixture_only": True},
    )


def _matrix() -> EvaluationMatrix:
    return EvaluationMatrix(
        configurations=(
            _config(
                "dense-fixed256",
                RetrievalPipeline.DENSE_ONLY,
                ChunkingStrategy.FIXED_256,
            ),
            _config(
                "hybrid-fixed512",
                RetrievalPipeline.HYBRID_RRF,
                ChunkingStrategy.FIXED_512,
            ),
            _config(
                "rerank-fixed1024",
                RetrievalPipeline.HYBRID_RERANK,
                ChunkingStrategy.FIXED_1024,
            ),
            _config(
                "rerank-semantic-expand",
                RetrievalPipeline.HYBRID_RERANK,
                ChunkingStrategy.SEMANTIC,
                query_expansion=True,
            ),
            _config(
                "rerank-table-aware-multihop",
                RetrievalPipeline.HYBRID_RERANK,
                ChunkingStrategy.TABLE_AWARE,
                query_expansion=True,
                multi_hop=True,
            ),
        )
    )


async def _report() -> dict[str, object]:
    records = load_evaluation_jsonl(FIXTURE_PATH)
    tracker = FakeExperimentTracker()
    runner = AsyncEvaluationRunner(
        observation_provider=FixtureObservationProvider(),
        engine=EvaluationEngine(judge=DeterministicRuleJudge()),
        tracker=tracker,
    )
    environment = build_environment(
        corpus_index_fingerprint=FIXTURE_INDEX_FINGERPRINT,
        repo_root=ROOT,
    )
    with tempfile.TemporaryDirectory(prefix="rageval-phase12-") as temp_dir:
        output_dir = Path(temp_dir)
        report = await runner.run_matrix(
            records,
            _matrix(),
            environment=environment,
            output_dir=output_dir,
            evidence_label="deterministic-fixture-ablation-mechanics-only",
            report_metadata={"target_dataset_supplied": False, "fixture_records": len(records)},
        )
        expected_files = {
            "json": output_dir / "ablation-report.json",
            "markdown": output_dir / "ablation-report.md",
            "html": output_dir / "ablation-report.html",
        }
        if not all(path.exists() for path in expected_files.values()):
            raise AssertionError("Phase 12 local report artifacts were not all produced")

        for run in report.runs:
            recomputed = aggregate_metric_slices(records, run.evaluation)
            if recomputed != run.metric_slices:
                raise AssertionError("Phase 12 summary values were not recomputed from records")

        run_ids = {run.run_id for run in report.runs}
        config_fingerprints = {run.config_fingerprint for run in report.runs}
        if len(run_ids) != len(report.runs) or len(config_fingerprints) != len(report.runs):
            raise AssertionError("Phase 12 fixture configurations did not produce distinct runs")
        if len(tracker.runs) != len(report.runs):
            raise AssertionError("experiment tracker did not receive one event per configuration")

        return {
            "schema_version": "1.0",
            "fixture_records": len(records),
            "target_dataset_supplied": False,
            "dataset_fingerprint": report.dataset_fingerprint,
            "matrix_fingerprint": report.matrix_fingerprint,
            "configuration_count": len(report.runs),
            "tracker_events": len(tracker.runs),
            "local_report_formats": sorted(expected_files),
            "configurations": [
                {
                    "config_id": run.config.config_id,
                    "run_id": run.run_id,
                    "config_fingerprint": run.config_fingerprint,
                    "pipeline": run.config.retrieval_pipeline.value,
                    "chunking": run.config.chunking_strategy.value,
                    "query_expansion": run.config.query_expansion,
                    "multi_hop": run.config.multi_hop,
                    "overall": {
                        item.metric: {"mean": item.mean_score, "count": item.count}
                        for item in run.metric_slices
                        if item.domain is None
                    },
                    "failure_categories": sorted(
                        {
                            category.value
                            for failure in run.failures
                            for category in failure.categories
                        }
                    ),
                }
                for run in report.runs
            ],
            "evidence_label": report.evidence_label,
        }


def main() -> None:
    print(json.dumps(asyncio.run(_report()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
