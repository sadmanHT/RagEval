"""Typed evidence contracts for Phase 15 full-system validation."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from rageval.models.contracts import ContractModel, Domain


class ValidationStatus(StrEnum):
    """Outcome of one deterministic validation scenario."""

    PASSED = "passed"
    BLOCKED = "blocked"


class LatencySummary(ContractModel):
    """Measured latency distribution using nearest-rank percentiles."""

    sample_count: int = Field(ge=1)
    minimum_ms: float = Field(ge=0.0)
    mean_ms: float = Field(ge=0.0)
    p50_ms: float = Field(ge=0.0)
    p95_ms: float = Field(ge=0.0)
    p99_ms: float = Field(ge=0.0)
    maximum_ms: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_order(self) -> LatencySummary:
        if not (self.minimum_ms <= self.p50_ms <= self.p95_ms <= self.p99_ms <= self.maximum_ms):
            raise ValueError("latency percentiles must be monotonic")
        return self


class ScenarioEvidence(ContractModel):
    """One named end-to-end or adversarial acceptance scenario."""

    name: str = Field(min_length=3)
    status: ValidationStatus
    domain: Domain | None = None
    details: dict[str, object] = Field(default_factory=dict)


class LoadEvidence(ContractModel):
    """Measured modest-concurrency API load evidence."""

    request_count: int = Field(ge=1)
    concurrency: int = Field(ge=1)
    wall_time_ms: float = Field(gt=0.0)
    requests_per_second: float = Field(gt=0.0)
    latency: LatencySummary


class BenchmarkEvidence(ContractModel):
    """Measured local fixture latency evidence, not a production SLO claim."""

    environment: dict[str, object]
    cold_api: LatencySummary
    cold_retrieval: LatencySummary
    cold_generation: LatencySummary
    warm_cache_api: LatencySummary
    concurrent_api: LoadEvidence
    methodology: str = Field(min_length=10)


class EvaluationEvidence(ContractModel):
    """Evidence recomputed from the available reviewed evaluation records."""

    reviewed_record_count: int = Field(ge=1)
    target_200_available: bool
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    hallucination_flagged_count: int = Field(ge=0)
    hallucination_total_count: int = Field(ge=0)
    hallucination_rate: float = Field(ge=0.0, le=1.0)
    resumed_examples: int = Field(ge=0)
    produced_examples_first_run: int = Field(ge=0)
    tracker: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hallucination_arithmetic(self) -> EvaluationEvidence:
        expected = (
            0.0
            if self.hallucination_total_count == 0
            else self.hallucination_flagged_count / self.hallucination_total_count
        )
        if abs(self.hallucination_rate - expected) > 1e-12:
            raise ValueError("hallucination rate must equal flagged_count / total_count")
        return self


class FullSystemValidationReport(ContractModel):
    """Machine-readable Phase 15 deterministic release evidence."""

    schema_version: str = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    git_commit: str = Field(min_length=1)
    evidence_label: str = Field(min_length=1)
    source_documents: int = Field(ge=1)
    canonical_chunks: int = Field(ge=1)
    scenarios: tuple[ScenarioEvidence, ...]
    benchmark: BenchmarkEvidence
    evaluation: EvaluationEvidence
    provider_validation: dict[str, str]
    blocked_validations: tuple[str, ...] = ()
    release_gate_passed: bool

    @model_validator(mode="after")
    def validate_release_gate(self) -> FullSystemValidationReport:
        deterministic_failures = [
            item.name for item in self.scenarios if item.status is not ValidationStatus.PASSED
        ]
        if self.release_gate_passed and deterministic_failures:
            raise ValueError(
                "release_gate_passed cannot be true with blocked/failed deterministic scenarios"
            )
        return self


def summarize_latency(samples_ms: list[float]) -> LatencySummary:
    """Summarize actual non-negative samples with nearest-rank percentiles."""

    if not samples_ms:
        raise ValueError("at least one latency sample is required")
    if any(value < 0 for value in samples_ms):
        raise ValueError("latency samples must be non-negative")
    ordered = sorted(float(value) for value in samples_ms)

    def percentile(q: float) -> float:
        rank = max(1, math.ceil(q * len(ordered)))
        return ordered[rank - 1]

    return LatencySummary(
        sample_count=len(ordered),
        minimum_ms=ordered[0],
        mean_ms=sum(ordered) / len(ordered),
        p50_ms=percentile(0.50),
        p95_ms=percentile(0.95),
        p99_ms=percentile(0.99),
        maximum_ms=ordered[-1],
    )
