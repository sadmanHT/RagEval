from __future__ import annotations

import pytest
from pydantic import ValidationError

from rageval.models import Domain
from rageval.validation import (
    EvaluationEvidence,
    FullSystemValidationReport,
    ScenarioEvidence,
    ValidationStatus,
    summarize_latency,
)


def test_summarize_latency_uses_actual_nearest_rank_samples() -> None:
    summary = summarize_latency([4.0, 1.0, 2.0, 3.0, 10.0])

    assert summary.sample_count == 5
    assert summary.minimum_ms == 1.0
    assert summary.p50_ms == 3.0
    assert summary.p95_ms == 10.0
    assert summary.p99_ms == 10.0
    assert summary.maximum_ms == 10.0
    assert summary.mean_ms == 4.0


def test_evaluation_evidence_rejects_inconsistent_hallucination_rate() -> None:
    with pytest.raises(ValidationError, match="flagged_count / total_count"):
        EvaluationEvidence(
            reviewed_record_count=3,
            target_200_available=False,
            dataset_fingerprint="a" * 64,
            hallucination_flagged_count=1,
            hallucination_total_count=3,
            hallucination_rate=0.5,
            resumed_examples=3,
            produced_examples_first_run=3,
            tracker="local-json",
        )


def test_release_gate_cannot_pass_with_blocked_deterministic_scenario() -> None:
    latency = summarize_latency([1.0])
    with pytest.raises(ValidationError, match="release_gate_passed"):
        FullSystemValidationReport(
            git_commit="abc",
            evidence_label="fixture-only",
            source_documents=4,
            canonical_chunks=6,
            scenarios=(
                ScenarioEvidence(
                    name="financial-domain",
                    status=ValidationStatus.PASSED,
                    domain=Domain.FINANCIAL,
                ),
                ScenarioEvidence(
                    name="required-deterministic-path",
                    status=ValidationStatus.BLOCKED,
                ),
            ),
            benchmark={
                "environment": {"python": "test"},
                "cold_api": latency,
                "cold_retrieval": latency,
                "cold_generation": latency,
                "warm_cache_api": latency,
                "concurrent_api": {
                    "request_count": 1,
                    "concurrency": 1,
                    "wall_time_ms": 1.0,
                    "requests_per_second": 1000.0,
                    "latency": latency,
                },
                "methodology": "deterministic unit fixture",
            },
            evaluation={
                "reviewed_record_count": 3,
                "target_200_available": False,
                "dataset_fingerprint": "a" * 64,
                "hallucination_flagged_count": 0,
                "hallucination_total_count": 3,
                "hallucination_rate": 0.0,
                "resumed_examples": 3,
                "produced_examples_first_run": 3,
                "tracker": "local-json",
            },
            provider_validation={},
            release_gate_passed=True,
        )
