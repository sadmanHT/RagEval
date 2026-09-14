"""Async checkpointed Phase 12 comparative evaluation runner."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from rageval.core.errors import EvaluationError
from rageval.core.protocols import ExperimentTracker
from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation.dataset import fingerprint_evaluation_records
from rageval.evaluation.engine import EvaluationEngine
from rageval.evaluation.failures import classify_failure
from rageval.evaluation.models import EvaluationObservation, EvaluationRun
from rageval.evaluation.run_models import (
    AblationConfiguration,
    ComparativeEvaluationReport,
    ConfigurationRun,
    EvaluationEnvironment,
    EvaluationMatrix,
    EvaluationRunnerConfig,
    MetricSlice,
    ObservationCheckpoint,
)
from rageval.models import Domain


class ObservationProvider(Protocol):
    """Produce one grounded system observation for one example/configuration pair."""

    @property
    def name(self) -> str: ...

    async def observe(
        self,
        record: EvaluationDatasetRecord,
        config: AblationConfiguration,
    ) -> EvaluationObservation: ...


@dataclass(frozen=True)
class _ObservationOutcome:
    example_id: str
    observation: EvaluationObservation | None
    resumed: bool
    error: Exception | None


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_ablation_config(config: AblationConfiguration) -> str:
    return _sha256_json(config.model_dump(mode="json"))


def fingerprint_evaluation_matrix(matrix: EvaluationMatrix) -> str:
    payload = [
        item.model_dump(mode="json")
        for item in sorted(matrix.configurations, key=lambda config: config.config_id)
    ]
    return _sha256_json(payload)


def detect_git_commit(repo_root: Path | None = None) -> str:
    """Return the actual Git SHA when available, otherwise the explicit value `unknown`."""

    github_sha = os.getenv("GITHUB_SHA", "").strip()
    if github_sha:
        return github_sha
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    commit = completed.stdout.strip()
    return commit or "unknown"


def machine_summary() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def build_environment(
    *,
    corpus_index_fingerprint: str,
    repo_root: Path | None = None,
    started_at: datetime | None = None,
) -> EvaluationEnvironment:
    return EvaluationEnvironment(
        git_commit=detect_git_commit(repo_root),
        corpus_index_fingerprint=corpus_index_fingerprint,
        started_at=started_at or datetime.now(UTC),
        machine_summary=machine_summary(),
    )


class CheckpointStore:
    """Per-example JSON checkpoints scoped by dataset and ablation configuration."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, config_id: str, example_id: str) -> Path:
        return self.root / config_id / f"{example_id}.json"

    async def load(
        self,
        *,
        config_id: str,
        example_id: str,
        dataset_fingerprint: str,
        config_fingerprint: str,
    ) -> ObservationCheckpoint | None:
        path = self._path(config_id, example_id)
        if not path.exists():
            return None
        raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
        try:
            checkpoint = ObservationCheckpoint.model_validate_json(raw)
        except ValueError as exc:
            raise EvaluationError(f"invalid checkpoint {path}: {exc}") from exc
        if checkpoint.example_id != example_id:
            raise EvaluationError(f"checkpoint example mismatch at {path}")
        if checkpoint.dataset_fingerprint != dataset_fingerprint:
            raise EvaluationError(
                f"checkpoint dataset fingerprint mismatch at {path}; delete stale checkpoint"
            )
        if checkpoint.config_fingerprint != config_fingerprint:
            raise EvaluationError(
                f"checkpoint config fingerprint mismatch at {path}; delete stale checkpoint"
            )
        return checkpoint

    async def save(
        self,
        *,
        config_id: str,
        checkpoint: ObservationCheckpoint,
    ) -> None:
        path = self._path(config_id, checkpoint.example_id)
        payload = checkpoint.model_dump_json(indent=2)
        await asyncio.to_thread(_write_atomic, path, payload)


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


async def _write_json(path: Path, payload: object) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    await asyncio.to_thread(_write_atomic, path, content)


def aggregate_metric_slices(
    records: Sequence[EvaluationDatasetRecord],
    run: EvaluationRun,
) -> tuple[MetricSlice, ...]:
    """Recompute overall/domain metrics from persisted per-example result records."""

    domain_by_id = {record.example.example_id: record.example.domain for record in records}
    values: dict[tuple[str, Domain | None], list[float]] = defaultdict(list)
    for example_record in run.records:
        try:
            domain = domain_by_id[example_record.example_id]
        except KeyError as exc:
            raise EvaluationError(
                f"evaluation run contains unknown example {example_record.example_id}"
            ) from exc
        for result in example_record.results:
            values[(result.metric, None)].append(result.score)
            values[(result.metric, domain)].append(result.score)

    return tuple(
        MetricSlice(
            metric=metric,
            domain=domain,
            count=len(scores),
            mean_score=sum(scores) / len(scores),
        )
        for (metric, domain), scores in sorted(
            values.items(),
            key=lambda item: (item[0][0], item[0][1].value if item[0][1] is not None else ""),
        )
    )


def _tracker_metrics(slices: Sequence[MetricSlice]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for item in slices:
        scope = "overall" if item.domain is None else item.domain.value
        metrics[f"{scope}.{item.metric}"] = item.mean_score
    return metrics


def _configuration_metadata(
    *,
    config: AblationConfiguration,
    environment: EvaluationEnvironment,
    dataset_fingerprint: str,
    config_fingerprint: str,
    engine_run: EvaluationRun,
    observation_provider: str,
) -> dict[str, object]:
    chunk_config: dict[str, object] = {
        "strategy": config.chunking_strategy.value,
        **config.chunk_config,
    }
    retrieval_params: dict[str, object] = {
        "pipeline": config.retrieval_pipeline.value,
        "query_expansion": config.query_expansion,
        "multi_hop": config.multi_hop,
        "candidate_top_k": config.candidate_top_k,
        "final_top_k": config.final_top_k,
        "rrf_k": config.rrf_k,
        **config.retrieval_params,
    }
    return {
        "git_commit": environment.git_commit,
        "dataset_fingerprint": dataset_fingerprint,
        "corpus_index_fingerprint": environment.corpus_index_fingerprint,
        "config_fingerprint": config_fingerprint,
        "provider_versions": dict(config.provider_versions),
        "prompt_versions": dict(config.prompt_versions),
        "chunk_config": chunk_config,
        "retrieval_params": retrieval_params,
        "timestamp": environment.started_at.isoformat(),
        "machine": dict(environment.machine_summary),
        "observation_provider": observation_provider,
        "judge_provider": engine_run.judge_provider,
        "judge_model": engine_run.judge_model,
        "metric_version": engine_run.metadata.get("metric_version", "unknown"),
    }


class AsyncEvaluationRunner:
    """Execute resumable configuration matrices with bounded per-example concurrency."""

    def __init__(
        self,
        *,
        observation_provider: ObservationProvider,
        engine: EvaluationEngine,
        config: EvaluationRunnerConfig | None = None,
        tracker: ExperimentTracker | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.observation_provider = observation_provider
        self.engine = engine
        self.config = config or EvaluationRunnerConfig()
        self.tracker = tracker
        self._sleeper = sleeper

    async def _produce_one(
        self,
        record: EvaluationDatasetRecord,
        ablation: AblationConfiguration,
        *,
        dataset_fingerprint: str,
        config_fingerprint: str,
        checkpoints: CheckpointStore,
        semaphore: asyncio.Semaphore,
    ) -> _ObservationOutcome:
        example_id = record.example.example_id
        try:
            checkpoint = await checkpoints.load(
                config_id=ablation.config_id,
                example_id=example_id,
                dataset_fingerprint=dataset_fingerprint,
                config_fingerprint=config_fingerprint,
            )
        except Exception as exc:
            return _ObservationOutcome(example_id, None, False, exc)
        if checkpoint is not None:
            if checkpoint.observation.example != record.example:
                error = EvaluationError(
                    f"checkpoint observation payload differs from dataset record for {example_id}"
                )
                return _ObservationOutcome(example_id, None, False, error)
            return _ObservationOutcome(example_id, checkpoint.observation, True, None)

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                async with semaphore:
                    observation = await self.observation_provider.observe(record, ablation)
                if observation.example != record.example:
                    raise EvaluationError(
                        f"observation provider changed the dataset example payload for {example_id}"
                    )
                checkpoint = ObservationCheckpoint(
                    example_id=example_id,
                    dataset_fingerprint=dataset_fingerprint,
                    config_fingerprint=config_fingerprint,
                    attempts=attempt,
                    observation=observation,
                )
                await checkpoints.save(config_id=ablation.config_id, checkpoint=checkpoint)
                return _ObservationOutcome(example_id, observation, False, None)
            except Exception as exc:
                last_error = exc
                if attempt < self.config.max_attempts:
                    delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                    await self._sleeper(delay)

        error = EvaluationError(
            f"example {example_id} failed after {self.config.max_attempts} attempts: {last_error}"
        )
        return _ObservationOutcome(example_id, None, False, error)

    async def _evaluate_with_retry(
        self,
        records: Sequence[EvaluationDatasetRecord],
        observations: Sequence[EvaluationObservation],
    ) -> EvaluationRun:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return await self.engine.evaluate(records, observations)
            except Exception as exc:
                last_error = exc
                if attempt < self.config.max_attempts:
                    delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                    await self._sleeper(delay)
        raise EvaluationError(
            f"evaluation engine failed after {self.config.max_attempts} attempts: {last_error}"
        ) from last_error

    async def run_configuration(
        self,
        records: Sequence[EvaluationDatasetRecord],
        ablation: AblationConfiguration,
        *,
        environment: EvaluationEnvironment,
        output_dir: Path,
    ) -> ConfigurationRun:
        if not records:
            raise EvaluationError("evaluation runner requires at least one dataset record")
        dataset_fingerprint = fingerprint_evaluation_records(records)
        config_fingerprint = fingerprint_ablation_config(ablation)
        checkpoints = CheckpointStore(output_dir / "checkpoints")
        semaphore = asyncio.Semaphore(self.config.max_concurrency)

        outcomes = await asyncio.gather(
            *(
                self._produce_one(
                    record,
                    ablation,
                    dataset_fingerprint=dataset_fingerprint,
                    config_fingerprint=config_fingerprint,
                    checkpoints=checkpoints,
                    semaphore=semaphore,
                )
                for record in sorted(records, key=lambda item: item.example.example_id)
            )
        )
        errors = [item.error for item in outcomes if item.error is not None]
        if errors:
            first = errors[0]
            raise EvaluationError(
                f"configuration {ablation.config_id} has {len(errors)} failed example(s): {first}"
            ) from first

        observations = [item.observation for item in outcomes if item.observation is not None]
        if len(observations) != len(records):
            raise EvaluationError("runner lost one or more observations before evaluation")
        engine_run = await self._evaluate_with_retry(records, observations)
        slices = aggregate_metric_slices(records, engine_run)

        record_by_id = {record.example.example_id: record for record in records}
        observation_by_id = {item.example.example_id: item for item in observations}
        failures = tuple(
            failure
            for evaluated in engine_run.records
            if (
                failure := classify_failure(
                    record_by_id[evaluated.example_id],
                    observation_by_id[evaluated.example_id],
                    evaluated,
                    ablation,
                )
            )
            is not None
        )
        metadata = _configuration_metadata(
            config=ablation,
            environment=environment,
            dataset_fingerprint=dataset_fingerprint,
            config_fingerprint=config_fingerprint,
            engine_run=engine_run,
            observation_provider=self.observation_provider.name,
        )
        run_id = _sha256_json(
            {
                "dataset_fingerprint": dataset_fingerprint,
                "config_fingerprint": config_fingerprint,
                "engine_run_fingerprint": engine_run.run_fingerprint,
                "git_commit": environment.git_commit,
                "corpus_index_fingerprint": environment.corpus_index_fingerprint,
            }
        )
        configuration_run = ConfigurationRun(
            run_id=run_id,
            config=ablation,
            dataset_fingerprint=dataset_fingerprint,
            config_fingerprint=config_fingerprint,
            evaluation=engine_run,
            metric_slices=slices,
            failures=failures,
            metadata=metadata,
            resumed_examples=sum(1 for item in outcomes if item.resumed),
            produced_examples=sum(1 for item in outcomes if not item.resumed),
        )
        await _write_json(
            output_dir / "runs" / f"{ablation.config_id}.json",
            configuration_run.model_dump(mode="json"),
        )
        if self.tracker is not None:
            tracker_metadata = dict(metadata)
            tracker_metadata["run_id"] = run_id
            await self.tracker.log_metrics(
                ablation.config_id,
                _tracker_metrics(slices),
                tracker_metadata,
            )
        return configuration_run

    async def run_matrix(
        self,
        records: Sequence[EvaluationDatasetRecord],
        matrix: EvaluationMatrix,
        *,
        environment: EvaluationEnvironment,
        output_dir: Path,
        evidence_label: str,
        report_metadata: Mapping[str, object] | None = None,
    ) -> ComparativeEvaluationReport:
        runs: list[ConfigurationRun] = []
        for ablation in matrix.configurations:
            runs.append(
                await self.run_configuration(
                    records,
                    ablation,
                    environment=environment,
                    output_dir=output_dir,
                )
            )

        report = ComparativeEvaluationReport(
            dataset_fingerprint=fingerprint_evaluation_records(records),
            matrix_fingerprint=fingerprint_evaluation_matrix(matrix),
            runs=tuple(runs),
            evidence_label=evidence_label,
            metadata={
                "configuration_count": len(runs),
                **dict(report_metadata or {}),
            },
        )
        from rageval.evaluation.reporting import write_comparative_reports

        await write_comparative_reports(report, output_dir)
        return report
