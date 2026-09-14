"""Small in-process abuse controls for the single-key serving boundary."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass


@dataclass
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    """Per-key fixed-window limiter with hashed identities and bounded state."""

    def __init__(self, *, max_requests: int, window_seconds: float) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> tuple[bool, int]:
        """Return whether the request is allowed and a conservative Retry-After."""

        now = time.monotonic()
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        async with self._lock:
            window = self._windows.get(digest)
            if window is None or now - window.started_at >= self.window_seconds:
                self._windows = {digest: _Window(started_at=now, count=1)}
                return True, 0
            if window.count < self.max_requests:
                window.count += 1
                return True, 0
            retry_after = max(int(self.window_seconds - (now - window.started_at)) + 1, 1)
            return False, retry_after
