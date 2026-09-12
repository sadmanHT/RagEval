"""Deterministic identity and fingerprint helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def stable_digest(*parts: str) -> str:
    """Return a stable SHA-256 digest for explicit ordered string parts."""
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fingerprint_mapping(values: Mapping[str, object]) -> str:
    """Fingerprint a mapping using canonical JSON ordering."""
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_document_id(*, checksum_sha256: str, source_uri: str) -> str:
    """Create a deterministic document identifier from immutable source identity."""
    return f"doc_{stable_digest(checksum_sha256, source_uri)[:32]}"


def make_element_id(
    *,
    document_id: str,
    ordinal: int,
    kind: str,
    text: str,
    page_number: int | None,
    config_fingerprint: str,
) -> str:
    """Create a deterministic element ID from source, order, type, content, and parser config."""
    digest = stable_digest(
        document_id,
        str(ordinal),
        kind,
        text,
        "" if page_number is None else str(page_number),
        config_fingerprint,
    )
    return f"elm_{digest[:32]}"


def make_chunk_id(*, document_id: str, ordinal: int, config_fingerprint: str, text: str) -> str:
    """Create a deterministic chunk identifier from document/config/content identity."""
    digest = stable_digest(document_id, str(ordinal), config_fingerprint, text)
    return f"chk_{digest[:32]}"
