"""Experiment-tracking adapters for Phase 12 evaluation runs."""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from rageval.core.errors import EvaluationError


class _WandbRun(Protocol):
    def log(self, data: Mapping[str, float]) -> object: ...

    def finish(self) -> object: ...


class _WandbModule(Protocol):
    def init(
        self,
        *,
        project: str,
        name: str,
        config: Mapping[str, object],
    ) -> _WandbRun: ...


class LocalJsonExperimentTracker:
    """Credential-free append-only experiment tracker used alongside local reports."""

    name = "local-json"

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def log_metrics(
        self,
        run_name: str,
        metrics: Mapping[str, float],
        metadata: Mapping[str, object],
    ) -> None:
        payload = {
            "run_name": run_name,
            "metrics": dict(metrics),
            "metadata": dict(metadata),
        }
        line = json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)


class WandbExperimentTracker:
    """Optional Weights & Biases adapter; import is lazy and never required for local CI."""

    name = "wandb"

    def __init__(
        self,
        *,
        project: str,
        module: _WandbModule | None = None,
    ) -> None:
        if not project.strip():
            raise ValueError("W&B project name cannot be blank")
        self.project = project.strip()
        self._module = module

    def _resolve_module(self) -> _WandbModule:
        if self._module is not None:
            return self._module
        try:
            imported = importlib.import_module("wandb")
        except ImportError as exc:
            raise EvaluationError(
                "Weights & Biases tracking requested but the optional wandb package "
                "is not installed"
            ) from exc
        return cast(_WandbModule, imported)

    async def log_metrics(
        self,
        run_name: str,
        metrics: Mapping[str, float],
        metadata: Mapping[str, object],
    ) -> None:
        module = self._resolve_module()
        await asyncio.to_thread(
            self._log_sync,
            module,
            run_name,
            dict(metrics),
            dict(metadata),
        )

    def _log_sync(
        self,
        module: _WandbModule,
        run_name: str,
        metrics: Mapping[str, float],
        metadata: Mapping[str, object],
    ) -> None:
        run = module.init(project=self.project, name=run_name, config=metadata)
        run.log(metrics)
        run.finish()
