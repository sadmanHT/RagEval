"""Bounded in-process evaluation job execution for Phase 13 serving."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from rageval.evaluation.run_models import ComparativeEvaluationReport
from rageval.serving.models import (
    EvaluationJobAccepted,
    EvaluationJobState,
    EvaluationJobStatus,
    EvaluationMetricSummary,
    EvaluationRunRequest,
    EvaluationSummary,
    utc_now,
)

logger = logging.getLogger(__name__)


class EvaluationJobExecutor(Protocol):
    async def run(self, request: EvaluationRunRequest) -> ComparativeEvaluationReport: ...


class EvaluationJobQueueFull(RuntimeError):
    """Raised when the bounded evaluation queue cannot accept another run."""


@dataclass
class _JobRecord:
    job_id: str
    request: EvaluationRunRequest
    status: EvaluationJobState
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: EvaluationSummary | None = None
    error_code: str | None = None


class EvaluationJobManager:
    """Fixed-worker queue so web requests cannot create unbounded evaluation tasks."""

    def __init__(
        self,
        *,
        executor: EvaluationJobExecutor,
        max_concurrency: int = 1,
        max_queue_size: int = 8,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be >= 1")
        self.executor = executor
        self.max_concurrency = max_concurrency
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue_size)
        self.records: dict[str, _JobRecord] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._latest: EvaluationSummary | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(), name=f"rageval-eval-worker-{index}")
            for index in range(self.max_concurrency)
        ]

    async def stop(self) -> None:
        workers, self._workers = self._workers, []
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    async def submit(self, request: EvaluationRunRequest) -> EvaluationJobAccepted:
        if not self._workers:
            raise RuntimeError("evaluation job manager is not started")
        job_id = uuid.uuid4().hex
        record = _JobRecord(
            job_id=job_id,
            request=request,
            status=EvaluationJobState.QUEUED,
            submitted_at=utc_now(),
        )
        async with self._lock:
            self.records[job_id] = record
            try:
                self.queue.put_nowait(job_id)
            except asyncio.QueueFull as exc:
                self.records.pop(job_id, None)
                raise EvaluationJobQueueFull("evaluation job queue is full") from exc
        return EvaluationJobAccepted(job_id=job_id, status=EvaluationJobState.QUEUED)

    async def status(self, job_id: str) -> EvaluationJobStatus | None:
        async with self._lock:
            record = self.records.get(job_id)
            if record is None:
                return None
            return EvaluationJobStatus(
                job_id=record.job_id,
                status=record.status,
                submitted_at=record.submitted_at,
                started_at=record.started_at,
                completed_at=record.completed_at,
                summary=record.summary,
                error_code=record.error_code,
            )

    async def latest(self) -> EvaluationSummary | None:
        async with self._lock:
            return self._latest

    async def _worker(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self._execute(job_id)
            finally:
                self.queue.task_done()

    async def _execute(self, job_id: str) -> None:
        async with self._lock:
            record = self.records[job_id]
            record.status = EvaluationJobState.RUNNING
            record.started_at = utc_now()
            request = record.request
        try:
            report = await self.executor.run(request)
            completed_at = utc_now()
            summary = _summarize_report(job_id, report, completed_at=completed_at)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "evaluation job failed",
                extra={
                    "context": {
                        "job_id": job_id,
                        "exception_type": type(exc).__name__,
                    }
                },
            )
            async with self._lock:
                record = self.records[job_id]
                record.status = EvaluationJobState.FAILED
                record.completed_at = utc_now()
                record.error_code = "evaluation_failed"
            return

        async with self._lock:
            record = self.records[job_id]
            record.status = EvaluationJobState.SUCCEEDED
            record.completed_at = completed_at
            record.summary = summary
            self._latest = summary


def _summarize_report(
    job_id: str,
    report: ComparativeEvaluationReport,
    *,
    completed_at: datetime,
) -> EvaluationSummary:
    metrics = tuple(
        EvaluationMetricSummary(
            config_id=run.config.config_id,
            metric=item.metric,
            domain=item.domain,
            count=item.count,
            mean_score=item.mean_score,
        )
        for run in report.runs
        for item in run.metric_slices
    )
    return EvaluationSummary(
        job_id=job_id,
        completed_at=completed_at,
        dataset_fingerprint=report.dataset_fingerprint,
        matrix_fingerprint=report.matrix_fingerprint,
        evidence_label=report.evidence_label,
        configuration_count=len(report.runs),
        metrics=metrics,
    )
