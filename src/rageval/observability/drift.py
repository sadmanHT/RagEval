"""Safe aggregate drift hooks for query and embedding distributions."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean


class DriftStatus(StrEnum):
    INSUFFICIENT_DATA = "insufficient_data"
    STABLE = "stable"
    POTENTIAL_SHIFT = "potential_shift"


@dataclass(frozen=True)
class DistributionSummary:
    count: int
    mean: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class DriftComparison:
    status: DriftStatus
    baseline: DistributionSummary
    current: DistributionSummary
    relative_mean_shift: float | None
    threshold: float
    min_samples: int


class SafeAggregateDriftMonitor:
    """Retain bounded numeric features only; never raw query text or embeddings."""

    def __init__(
        self,
        *,
        min_samples: int = 30,
        relative_shift_threshold: float = 0.25,
        max_samples: int = 10_000,
    ) -> None:
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if relative_shift_threshold < 0:
            raise ValueError("relative_shift_threshold must be >= 0")
        if max_samples < min_samples:
            raise ValueError("max_samples must be >= min_samples")
        self.min_samples = min_samples
        self.relative_shift_threshold = relative_shift_threshold
        self._baseline_query_lengths: deque[float] = deque(maxlen=max_samples)
        self._current_query_lengths: deque[float] = deque(maxlen=max_samples)
        self._baseline_embedding_norms: deque[float] = deque(maxlen=max_samples)
        self._current_embedding_norms: deque[float] = deque(maxlen=max_samples)

    def observe_query(self, query: str, *, baseline: bool = False) -> None:
        target = self._baseline_query_lengths if baseline else self._current_query_lengths
        target.append(float(len(query)))

    def observe_embedding(self, vector: Sequence[float], *, baseline: bool = False) -> None:
        norm = math.sqrt(sum(value * value for value in vector))
        target = self._baseline_embedding_norms if baseline else self._current_embedding_norms
        target.append(norm)

    def compare_query_lengths(self) -> DriftComparison:
        return self._compare(self._baseline_query_lengths, self._current_query_lengths)

    def compare_embedding_norms(self) -> DriftComparison:
        return self._compare(self._baseline_embedding_norms, self._current_embedding_norms)

    def _compare(
        self,
        baseline_values: Sequence[float],
        current_values: Sequence[float],
    ) -> DriftComparison:
        baseline = _summary(baseline_values)
        current = _summary(current_values)
        if baseline.count < self.min_samples or current.count < self.min_samples:
            return DriftComparison(
                status=DriftStatus.INSUFFICIENT_DATA,
                baseline=baseline,
                current=current,
                relative_mean_shift=None,
                threshold=self.relative_shift_threshold,
                min_samples=self.min_samples,
            )
        denominator = max(abs(baseline.mean), 1e-12)
        relative_shift = abs(current.mean - baseline.mean) / denominator
        status = (
            DriftStatus.POTENTIAL_SHIFT
            if relative_shift > self.relative_shift_threshold
            else DriftStatus.STABLE
        )
        return DriftComparison(
            status=status,
            baseline=baseline,
            current=current,
            relative_mean_shift=relative_shift,
            threshold=self.relative_shift_threshold,
            min_samples=self.min_samples,
        )


def _summary(values: Sequence[float]) -> DistributionSummary:
    if not values:
        return DistributionSummary(count=0, mean=0.0, minimum=0.0, maximum=0.0)
    return DistributionSummary(
        count=len(values),
        mean=fmean(values),
        minimum=min(values),
        maximum=max(values),
    )
