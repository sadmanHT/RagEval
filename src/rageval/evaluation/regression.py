"""Thresholded regression comparison for PR gates and nightly/full alerts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from enum import StrEnum

from pydantic import Field

from rageval.evaluation.run_models import MetricSlice
from rageval.models import Domain
from rageval.models.contracts import ContractModel


class RegressionMode(StrEnum):
    PR_FAST = "pr_fast"
    NIGHTLY_FULL = "nightly_full"


class RegressionStatus(StrEnum):
    STABLE = "stable"
    IMPROVEMENT = "improvement"
    DEGRADATION = "degradation"
    MISSING_METRIC = "missing_metric"
    SAMPLE_SIZE_MISMATCH = "sample_size_mismatch"


class RegressionThreshold(ContractModel):
    metric: str = Field(min_length=1)
    domain: Domain | None = None
    max_drop: float = Field(default=0.0, ge=0, le=1)
    min_score: float | None = Field(default=None, ge=0, le=1)
    min_samples: int = Field(default=1, ge=1)


class RegressionPolicy(ContractModel):
    schema_version: str = "1.0"
    mode: RegressionMode
    thresholds: tuple[RegressionThreshold, ...]


class RegressionFinding(ContractModel):
    metric: str
    domain: Domain | None = None
    status: RegressionStatus
    baseline_score: float | None = None
    candidate_score: float | None = None
    delta: float | None = None
    baseline_count: int | None = None
    candidate_count: int | None = None
    max_drop: float
    min_score: float | None = None
    min_samples: int
    blocking: bool = False
    alert: bool = False
    detail: str


class RegressionComparison(ContractModel):
    schema_version: str = "1.0"
    mode: RegressionMode
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    findings: tuple[RegressionFinding, ...]
    gate_failed: bool
    alert_triggered: bool


def fingerprint_regression_policy(policy: RegressionPolicy) -> str:
    payload = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _slice_map(slices: Sequence[MetricSlice]) -> dict[tuple[str, Domain | None], MetricSlice]:
    return {(item.metric, item.domain): item for item in slices}


def compare_metric_slices(
    baseline: Sequence[MetricSlice],
    candidate: Sequence[MetricSlice],
    policy: RegressionPolicy,
) -> RegressionComparison:
    """Compare configured metric slices while separating PR blocking from nightly alerts."""

    baseline_by_key = _slice_map(baseline)
    candidate_by_key = _slice_map(candidate)
    findings: list[RegressionFinding] = []

    for threshold in policy.thresholds:
        key = (threshold.metric, threshold.domain)
        before = baseline_by_key.get(key)
        after = candidate_by_key.get(key)
        status = RegressionStatus.STABLE
        detail = "metric stayed within configured regression limits"
        delta: float | None = None
        violation = False

        if before is None or after is None:
            status = RegressionStatus.MISSING_METRIC
            detail = "baseline or candidate is missing the configured metric slice"
            violation = True
        elif (
            before.count != after.count
            or before.count < threshold.min_samples
            or after.count < threshold.min_samples
        ):
            status = RegressionStatus.SAMPLE_SIZE_MISMATCH
            detail = (
                "sample counts differ or do not satisfy the configured minimum; "
                f"baseline={before.count} candidate={after.count} "
                f"minimum={threshold.min_samples}"
            )
            violation = True
        else:
            delta = after.mean_score - before.mean_score
            below_floor = threshold.min_score is not None and after.mean_score < threshold.min_score
            excessive_drop = delta < -threshold.max_drop
            if below_floor or excessive_drop:
                status = RegressionStatus.DEGRADATION
                detail = f"candidate delta={delta:.6f} exceeded max_drop={threshold.max_drop:.6f}"
                if below_floor:
                    detail += f" or fell below min_score={threshold.min_score:.6f}"
                violation = True
            elif delta > 0:
                status = RegressionStatus.IMPROVEMENT
                detail = f"candidate improved by {delta:.6f}"

        blocking = violation and policy.mode is RegressionMode.PR_FAST
        alert = violation and policy.mode is RegressionMode.NIGHTLY_FULL
        findings.append(
            RegressionFinding(
                metric=threshold.metric,
                domain=threshold.domain,
                status=status,
                baseline_score=before.mean_score if before is not None else None,
                candidate_score=after.mean_score if after is not None else None,
                delta=delta,
                baseline_count=before.count if before is not None else None,
                candidate_count=after.count if after is not None else None,
                max_drop=threshold.max_drop,
                min_score=threshold.min_score,
                min_samples=threshold.min_samples,
                blocking=blocking,
                alert=alert,
                detail=detail,
            )
        )

    return RegressionComparison(
        mode=policy.mode,
        policy_fingerprint=fingerprint_regression_policy(policy),
        findings=tuple(findings),
        gate_failed=any(item.blocking for item in findings),
        alert_triggered=any(item.alert for item in findings),
    )
