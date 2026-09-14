from __future__ import annotations

import json
from pathlib import Path

import pytest

from rageval.evaluation import (
    AblationConfiguration,
    ChunkingStrategy,
    ComparativeEvaluationReport,
    ConfigurationRun,
    EvaluationRun,
    HallucinationSummary,
    LocalJsonExperimentTracker,
    RetrievalPipeline,
    write_comparative_reports,
)
from rageval.testing.fakes import FakeExperimentTracker


def _configuration_run() -> ConfigurationRun:
    evaluation = EvaluationRun(
        dataset_fingerprint="a" * 64,
        config_fingerprint="b" * 64,
        run_fingerprint="c" * 64,
        judge_provider="fixture",
        judge_model="fixture-v1",
        records=(),
        aggregates=(),
        hallucination=HallucinationSummary(
            threshold=0.8,
            flagged_count=0,
            total_count=0,
            rate=0.0,
        ),
    )
    return ConfigurationRun(
        run_id="d" * 64,
        config=AblationConfiguration(
            config_id="report-fixture",
            retrieval_pipeline=RetrievalPipeline.DENSE_ONLY,
            chunking_strategy=ChunkingStrategy.FIXED_512,
        ),
        dataset_fingerprint="a" * 64,
        config_fingerprint="e" * 64,
        evaluation=evaluation,
        metric_slices=(),
    )


@pytest.mark.asyncio
async def test_report_writer_produces_json_markdown_and_html(tmp_path: Path) -> None:
    report = ComparativeEvaluationReport(
        dataset_fingerprint="a" * 64,
        matrix_fingerprint="f" * 64,
        runs=(_configuration_run(),),
        evidence_label="unit-test-mechanics-only",
    )
    paths = await write_comparative_reports(report, tmp_path)

    assert {path.suffix for path in paths} == {".json", ".md", ".html"}
    payload = json.loads((tmp_path / "ablation-report.json").read_text(encoding="utf-8"))
    assert payload["evidence_label"] == "unit-test-mechanics-only"
    assert "report-fixture" in (tmp_path / "ablation-report.md").read_text(encoding="utf-8")
    assert "report-fixture" in (tmp_path / "ablation-report.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_local_json_tracker_and_existing_fake_tracker(tmp_path: Path) -> None:
    local = LocalJsonExperimentTracker(tmp_path / "experiments.jsonl")
    await local.log_metrics("run-a", {"faithfulness": 0.75}, {"git_commit": "abc123"})
    lines = (tmp_path / "experiments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["metrics"]["faithfulness"] == 0.75

    fake = FakeExperimentTracker()
    await fake.log_metrics("run-b", {"context_recall": 1.0}, {"fixture": True})
    assert len(fake.runs) == 1
    assert fake.runs[0][0] == "run-b"
