"""Deterministic tokenization and sentence-boundary helpers for chunking."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from rageval.models.contracts import Domain

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[])")
_LEGAL_CLAUSE_RE = re.compile(r"^\s*(?:section\s+)?\d+(?:\.\d+)+\b", re.IGNORECASE)


@runtime_checkable
class Tokenizer(Protocol):
    """Minimal tokenizer boundary used by deterministic chunkers."""

    @property
    def name(self) -> str:
        """Stable tokenizer identifier included in chunk metadata."""
        ...

    def tokenize(self, text: str) -> tuple[str, ...]:
        """Tokenize normalized text in deterministic order."""
        ...

    def detokenize(self, tokens: tuple[str, ...]) -> str:
        """Reconstruct normalized chunk text from tokens."""
        ...


class WhitespaceTokenizer:
    """Offline deterministic token baseline for controlled chunk-size ablations."""

    name = "whitespace-v1"

    def tokenize(self, text: str) -> tuple[str, ...]:
        return tuple(text.split())

    def detokenize(self, tokens: tuple[str, ...]) -> str:
        return " ".join(tokens)


def starts_legal_clause(text: str) -> bool:
    """Return whether text begins with a numbered legal-clause style label."""
    return bool(_LEGAL_CLAUSE_RE.match(text))


def sentence_segments(
    text: str,
    *,
    domain: Domain,
    preserve_legal_clause: bool,
) -> tuple[str, ...]:
    """Split normalized prose on conservative sentence boundaries."""
    stripped = text.strip()
    if not stripped:
        return ()
    if domain is Domain.LEGAL and preserve_legal_clause and starts_legal_clause(stripped):
        return (stripped,)
    return tuple(
        segment.strip() for segment in _SENTENCE_BOUNDARY_RE.split(stripped) if segment.strip()
    )
