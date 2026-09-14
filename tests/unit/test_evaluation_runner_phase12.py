from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from rageval.core.errors import EvaluationError
from rageval.corpus.models import EvaluationDatasetRecord
from rageval.evaluation import (
    AblationConfiguration,
    AsyncEvaluationRunner,
    ChunkingStrategy,
    DeterministicRuleJudge,
    EvaluationEngine,
    EvaluationEnvironment,
    EvaluationMatrix,
    EvaluationObservation,
    EvaluationRunnerConfig,
    RetrievalPipeline,
)
from rageval.models import Citation, Domain, EvaluationExample, GroundedAnswer


def _record(index: int) -> EvaluationDatasetRecord:
    example_id = f"eval_runner_{index:04d}"
    support = f"chk_support_{index:04d}"
    return EvaluationDatasetRecord(
        example=EvaluationExample(
            example_id=example_id,
            question=f"What is fact {index}?",
            reference_answer=f"Fact {index} is supported.",
            domain=(Domain.FINANCIAL, Domain.LEGAL, Domain.RESEARCH)[index % 3],
            supporting_document_ids=[f"doc_eval_{index:04d}"],
            supporting_chunk_ids=[support],
            reviewer_status="approved",
            reviewer="phase12-test",
        ),
        supporting_document_ids=(f"doc_eval_{index:04d}",),
        corpus_fingerprint="a" * 64,
    )


def _observation(record: EvaluationDatasetRecord) -> EvaluationObservation:
    support = record.example.supporting_chunk_ids[0]
    return EvaluationObservation(
        example=record.example,
        answer=GroundedAnswer(
            question=record.example.question,
            answer=record.example.reference_answer,
            citations=[Citation(chunk_id=support, claim=record.example.reference_answer)],
            cited_chunk_ids=[support],
            provider="phase12-test",
            model="deterministic-v1",
            latency_ms=1.0,
        ),
        retrieved_chunk_ids=(support,),
        context_by_chunk_id={support: record.example.reference_answer},
    )


def _config(config_id: str = "dense-fixed512") -> AblationConfiguration:
    return AblationConfiguration(
        config_id=config_id,
        retrieval_pipeline=RetrievalPipeline.DENSE_ONLY,
        chunking_strategy=ChunkingStrategy.FIXED_512,
    )


def _environment() -> EvaluationEnvironment:
    return EvaluationEnvironment(
        git_commit="abc123def456",
        corpus_index_fingerprint="b" * 64,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        machine_summary={"fixture": True},
    )


class RecordingProvider:
    name = "recording-provider"

    def __init__(self, *, fail_example: str | None = None, delay: float = 0.0) -> None:
        self.fail_example = fail_example
        self.delay = delay
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def observe(
        self,
        record: EvaluationDatasetRecord,
        config: AblationConfiguration,
    ) -> EvaluationObservation:
        del config
        example_id = record.example.example_id
        self.calls.append(example_id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if example_id == self.fail_example:
                raise RuntimeError("injected observation failure")
            return _observation(record)
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_runner_resumes_completed_examples_after_injected_failure(tmp_path: Path) -> None:
    records = [_record(1), _record(2), _record(3)]
    failing = RecordingProvider(fail_example="eval_runner_0002")
    first_runner = AsyncEvaluationRunner(
        observation_provider=failing,
        engine=EvaluationEngine(judge=DeterministicRuleJudge()),
        config=EvaluationRunnerConfig(max_concurrency=3, max_attempts=1),
    )
    with pytest.raises(EvaluationError, match="1 failed example"):
        await first_runner.run_configuration(
            records,
            _config(),
            environment=_environment(),
            output_dir=tmp_path,
        )

    resumed_provider = RecordingProvider()
    second_runner = AsyncEvaluationRunner(
        observation_provider=resumed_provider,
        engine=EvaluationEngine(judge=DeterministicRuleJudge()),
        config=EvaluationRunnerConfig(max_concurrency=3, max_attempts=1),
    )
    run = await second_runner.run_configuration(
        records,
        _config(),
        environment=_environment(),
        output_dir=tmp_path,
    )

    assert resumed_provider.calls == ["eval_runner_0002"]
    assert run.resumed_examples == 2
    assert run.produced_examples == 1
    assert len(run.evaluation.records) == 3


@pytest.mark.asyncio
async def test_runner_enforces_concurrency_limit_and_deterministic_order(tmp_path: Path) -> None:
    records = [_record(index) for index in range(1, 7)]
    provider = RecordingProvider(delay=0.02)
    runner = AsyncEvaluationRunner(
        observation_provider=provider,
        engine=EvaluationEngine(judge=DeterministicRuleJudge()),
        config=EvaluationRunnerConfig(max_concurrency=2, max_attempts=1),
    )
    run = await runner.run_configuration(
        list(reversed(records)),
        _config(),
        environment=_environment(),
        output_dir=tmp_path,
    )

    assert provider.max_active <= 2
    assert [item.example_id for item in run.evaluation.records] == sorted(
        record.example.example_id for record in records
    )
    assert all(item.count > 0 for item in run.metric_slices)


class FailFirstAttemptProvider(RecordingProvider):
    def __init__(self) -> None:
        super().__init__()
        self._failed = False

    async def observe(
        self,
        record: EvaluationDatasetRecord,
        config: AblationConfiguration,
    ) -> EvaluationObservation:
        if not self._failed:
            self._failed = True
            self.calls.append(record.example.example_id)
            raise RuntimeError("transient fixture failure")
        return await super().observe(record, config)


@pytest.mark.asyncio
async def test_runner_retries_transient_example_failure(tmp_path: Path) -> None:
    provider = FailFirstAttemptProvider()
    runner = AsyncEvaluationRunner(
        observation_provider=provider,
        engine=EvaluationEngine(judge=DeterministicRuleJudge()),
        config=EvaluationRunnerConfig(
            max_concurrency=1,
            max_attempts=2,
            retry_backoff_seconds=0,
        ),
    )
    run = await runner.run_configuration(
        [_record(1)],
        _config(),
        environment=_environment(),
        output_dir=tmp_path,
    )

    assert provider.calls == ["eval_runner_0001", "eval_runner_0001"]
    assert run.produced_examples == 1


def test_evaluation_matrix_rejects_duplicate_config_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate config IDs"):
        EvaluationMatrix(configurations=(_config(), _config()))
