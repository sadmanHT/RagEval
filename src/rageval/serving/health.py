"""Async dependency health probes for Phase 13 serving."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from rageval.serving.models import ComponentHealth, HealthResponse


class AsyncHealthCheck(Protocol):
    async def __call__(self) -> None: ...


class HealthRegistry:
    """Named readiness checks with stable degraded/ok output."""

    def __init__(self, checks: Mapping[str, AsyncHealthCheck]) -> None:
        self.checks = dict(checks)

    async def readiness(self) -> HealthResponse:
        components: dict[str, ComponentHealth] = {}
        for name, check in self.checks.items():
            try:
                await check()
            except Exception:
                components[name] = ComponentHealth.DEGRADED
            else:
                components[name] = ComponentHealth.OK
        overall = (
            ComponentHealth.OK
            if all(status is ComponentHealth.OK for status in components.values())
            else ComponentHealth.DEGRADED
        )
        return HealthResponse(status=overall, components=components)


class CallableHealthCheck:
    """Adapt an async callable into the health-check protocol."""

    def __init__(self, callback: Callable[[], Awaitable[None]]) -> None:
        self.callback = callback

    async def __call__(self) -> None:
        await self.callback()


class StaticHealthCheck:
    """Deterministic provider readiness used for local/fake providers."""

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy

    async def __call__(self) -> None:
        if not self.healthy:
            raise RuntimeError("dependency unavailable")
