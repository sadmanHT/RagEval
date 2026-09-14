#!/usr/bin/env python3
"""Persist the available reviewed-set ablation and compute fixture-local domain winners."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import evaluation_ablation_fixture_report as phase12
from rageval.evaluation import (
    AsyncEvaluationRunner,
    DeterministicRuleJudge,
    EvaluationEngine,
    LocalJsonExperimentTracker,
    aggregate_metric_slices,
    build_environment,
    load_evaluation_jsonl,
)

QUALITY_METRICS = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Persistent directory for checkpoints, raw runs, reports, and tracker events.",
    )
    return parser.parse_args()


async def _run(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_evaluation_jsonl(phase12.FIXTURE_PATH)
    tracker = LocalJsonExperimentTracker(output_dir / "experiment-tracker.jsonl")
    runner = AsyncEvaluationRunner(
        observation_provider=phase12.FixtureObservationProvider(),
        engine=EvaluationEngine(judge=DeterministicRuleJudge()),
        tracker=tracker,
    )
    environment = build_environment(
        corpus_index_fingerprint=phase12.FIXTURE_INDEX_FINGERPRINT,
        repo_root=phase12.ROOT,
    )
    report = await runner.run_matrix(
        records,
        phase12._matrix(),
        environment=environment,
        output_dir=output_dir,
        evidence_label="phase15-reviewed-three-record-ablation-mechanics-only",
        report_metadata={
            "target_dataset_supplied": False,
            "reviewed_fixture_records": len(records),
            "domain_composite_metrics": list(QUALITY_METRICS),
            "tracker": "local-json",
        },
    )

    for run in report.runs:
        if aggregate_metric_slices(records, run.evaluation) != run.metric_slices:
            raise AssertionError("ablation summary was not recomputed from raw per-example records")

    domain_scores: dict[str, dict[str, float]] = {}
    for run in report.runs:
        by_domain: dict[str, list[float]] = {}
        for item in run.metric_slices:
            if item.domain is None or item.metric not in QUALITY_METRICS:
                continue
            by_domain.setdefault(item.domain.value, []).append(item.mean_score)
        domain_scores[run.config.config_id] = {
            domain: sum(values) / len(values)
            for domain, values in by_domain.items()
            if values
        }

    domains = sorted({domain for scores in domain_scores.values() for domain in scores})
    winners: dict[str, dict[str, object]] = {}
    for domain in domains:
        best = max(scores.get(domain, -1.0) for scores in domain_scores.values())
        winning_runs = [
            run
            for run in report.runs
            if abs(domain_scores[run.config.config_id].get(domain, -1.0) - best) <= 1e-12
        ]
        winners[domain] = {
            "composite_mean": best,
            "config_ids": [run.config.config_id for run in winning_runs],
            "chunking_strategies": sorted(
                {run.config.chunking_strategy.value for run in winning_runs}
            ),
            "note": (
                "fixture-local one-example-per-domain result; not a production strategy selection"
            ),
        }

    configurations = []
    for run in report.runs:
        hallucination = run.evaluation.hallucination
        configurations.append(
            {
                "config_id": run.config.config_id,
                "chunking_strategy": run.config.chunking_strategy.value,
                "retrieval_pipeline": run.config.retrieval_pipeline.value,
                "query_expansion": run.config.query_expansion,
                "multi_hop": run.config.multi_hop,
                "config_fingerprint": run.config_fingerprint,
                "run_id": run.run_id,
                "resumed_examples": run.resumed_examples,
                "produced_examples": run.produced_examples,
                "hallucination": {
                    "flagged_count": hallucination.flagged_count,
                    "total_count": hallucination.total_count,
                    "rate": hallucination.rate,
                },
                "domain_composite": domain_scores[run.config.config_id],
                "failure_categories": sorted(
                    {
                        category.value
                        for failure in run.failures
                        for category in failure.categories
                    }
                ),
            }
        )

    result = {
        "schema_version": "1.0",
        "reviewed_record_count": len(records),
        "target_200_available": False,
        "dataset_fingerprint": report.dataset_fingerprint,
        "matrix_fingerprint": report.matrix_fingerprint,
        "configuration_count": len(report.runs),
        "domain_composite_metrics": list(QUALITY_METRICS),
        "fixture_local_domain_winners": winners,
        "configurations": configurations,
        "artifact_files": {
            "report_json": str(output_dir / "ablation-report.json"),
            "report_markdown": str(output_dir / "ablation-report.md"),
            "report_html": str(output_dir / "ablation-report.html"),
            "runs_dir": str(output_dir / "runs"),
            "checkpoints_dir": str(output_dir / "checkpoints"),
            "tracker": str(output_dir / "experiment-tracker.jsonl"),
        },
        "evidence_label": report.evidence_label,
    }
    (output_dir / "phase15-reconciliation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> None:
    args = _args()
    print(json.dumps(asyncio.run(_run(args.output_dir)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
