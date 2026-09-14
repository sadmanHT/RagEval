from __future__ import annotations

import pytest

from rageval.evaluation import (
    MetricSlice,
    RegressionMode,
    RegressionPolicy,
    RegressionStatus,
    RegressionThreshold,
    compare_metric_slices,
)
from rageval.models import Domain


def _slice(score: float, *, count: int = 20) -> MetricSlice:
    return MetricSlice(metric="faithfulness", count=count, mean_score=score)


def test_regression_comparator_reports_improvement() -> None:
    comparison = compare_metric_slices(
        [_slice(0.80)],
        [_slice(0.85)],
        RegressionPolicy(
            mode=RegressionMode.PR_FAST,
            thresholds=(RegressionThreshold(metric="faithfulness", max_drop=0.02),),
        ),
    )
    assert comparison.findings[0].status is RegressionStatus.IMPROVEMENT
    assert comparison.findings[0].delta == pytest.approx(0.05)
    assert not comparison.gate_failed
    assert not comparison.alert_triggered


def test_pr_fast_degradation_is_blocking() -> None:
    comparison = compare_metric_slices(
        [_slice(0.90)],
        [_slice(0.80)],
        RegressionPolicy(
            mode=RegressionMode.PR_FAST,
            thresholds=(RegressionThreshold(metric="faithfulness", max_drop=0.03),),
        ),
    )
    finding = comparison.findings[0]
    assert finding.status is RegressionStatus.DEGRADATION
    assert finding.blocking
    assert comparison.gate_failed
    assert not comparison.alert_triggered


def test_nightly_degradation_alerts_but_does_not_fail_pr_gate() -> None:
    comparison = compare_metric_slices(
        [_slice(0.90)],
        [_slice(0.80)],
        RegressionPolicy(
            mode=RegressionMode.NIGHTLY_FULL,
            thresholds=(RegressionThreshold(metric="faithfulness", max_drop=0.03),),
        ),
    )
    assert comparison.findings[0].alert
    assert not comparison.gate_failed
    assert comparison.alert_triggered


def test_regression_comparator_reports_missing_metric() -> None:
    comparison = compare_metric_slices(
        [_slice(0.90)],
        [],
        RegressionPolicy(
            mode=RegressionMode.PR_FAST,
            thresholds=(RegressionThreshold(metric="faithfulness"),),
        ),
    )
    assert comparison.findings[0].status is RegressionStatus.MISSING_METRIC
    assert comparison.gate_failed


def test_regression_comparator_reports_sample_size_mismatch() -> None:
    baseline = MetricSlice(
        metric="context_recall",
        domain=Domain.LEGAL,
        count=10,
        mean_score=0.8,
    )
    candidate = baseline.model_copy(update={"count": 9, "mean_score": 0.82})
    comparison = compare_metric_slices(
        [baseline],
        [candidate],
        RegressionPolicy(
            mode=RegressionMode.PR_FAST,
            thresholds=(
                RegressionThreshold(
                    metric="context_recall",
                    domain=Domain.LEGAL,
                    min_samples=5,
                ),
            ),
        ),
    )
    assert comparison.findings[0].status is RegressionStatus.SAMPLE_SIZE_MISMATCH
    assert comparison.gate_failed
