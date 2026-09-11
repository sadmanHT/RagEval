"""Structured logging with conservative secret redaction."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_FRAGMENTS = ("api_key", "apikey", "token", "secret", "password", "authorization")
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[=:]\s*([^\s,;]+)"
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS)


def redact(value: Any) -> Any:
    """Recursively redact likely secrets from structured logging values."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(r"\1=[REDACTED]", value)
    return value


class SecretRedactionFilter(logging.Filter):
    """Redact message arguments before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        if record.args:
            record.args = redact(record.args)
        if hasattr(record, "context"):
            record.context = redact(record.context)
        return True


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter with stable fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        context = getattr(record, "context", None)
        if context is not None:
            payload["context"] = redact(context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root JSON logging exactly once for the current process."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
