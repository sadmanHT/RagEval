from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from pydantic import SecretStr

from rageval.core.settings import Settings
from rageval.evaluation import (
    AblationConfiguration,
    ChunkingStrategy,
    ComparativeEvaluationReport,
    ConfigurationRun,
    EvaluationRun,
    HallucinationSummary,
    RetrievalPipeline,
)
from rageval.serving import (
    EvaluationJobManager,
    MemoryQueryCache,
    QueryCacheIdentity,
    ServingDependencies,
    create_app,
)
from rageval.serving.models import EvaluationRunRequest


class _UnusedQueryService:
    async def answer(self, question: str, *, filters=None, top_k=None):
        del question, filters, top_k
        raise AssertionError("query service should not be called by readiness test")


class _FailingCache(MemoryQueryCache):
    async def ping(self) -> None:
        raise RuntimeError("redis unavailable")


def _report() -> ComparativeEvaluationReport:
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
    run = ConfigurationRun(
        run_id="d" * 64,
        config=AblationConfiguration(
            config_id="phase13-worker",
            retrieval_pipeline=RetrievalPipeline.DENSE_ONLY,
            chunking_strategy=ChunkingStrategy.FIXED_512,
        ),
        dataset_fingerprint="a" * 64,
        config_fingerprint="e" * 64,
        evaluation=evaluation,
    )
    return ComparativeEvaluationReport(
        dataset_fingerprint="a" * 64,
        matrix_fingerprint="f" * 64,
        runs=(run,),
        evidence_label="phase13-worker-fixture",
    )


class _ImmediateExecutor:
    async def run(self, request: EvaluationRunRequest) -> ComparativeEvaluationReport:
        del request
        return _report()


class _RecordingExecutor:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def run(self, request: EvaluationRunRequest) -> ComparativeEvaluationReport:
        del request
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.02)
            return _report()
        finally:
            self.active -= 1


def test_readiness_reports_configured_redis_degradation() -> None:
    app = create_app(
        dependencies=ServingDependencies(
            query_service=_UnusedQueryService(),
            evaluation_executor=_ImmediateExecutor(),
            cache_identity=QueryCacheIdentity(
                index_fingerprint="1" * 64,
                retrieval_config_fingerprint="2" * 64,
                generation_config_fingerprint="3" * 64,
                model_version="fixture-v1",
                prompt_version="prompt-v1",
            ),
            cache=_FailingCache(),
        ),
        settings=Settings(serving_api_key=SecretStr("phase13-health-secret")),
    )
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["components"]["redis"] == "degraded"


async def test_evaluation_workers_enforce_configured_concurrency() -> None:
    executor = _RecordingExecutor()
    manager = EvaluationJobManager(
        executor=executor,
        max_concurrency=1,
        max_queue_size=4,
    )
    await manager.start()
    try:
        jobs = [await manager.submit(EvaluationRunRequest()) for _ in range(3)]
        for _ in range(100):
            statuses = [await manager.status(job.job_id) for job in jobs]
            if all(status is not None and status.status.value == "succeeded" for status in statuses):
                break
            await asyncio.sleep(0.01)
        assert all(status is not None and status.status.value == "succeeded" for status in statuses)
        assert executor.max_active == 1
    finally:
        await manager.stop()
