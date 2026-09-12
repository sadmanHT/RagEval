"""Domain-aware lexical tokenization for BM25 retrieval."""

from __future__ import annotations

import re
from collections.abc import Iterable

from rageval.models.contracts import Domain
from rageval.retrieval.sparse.models import SparseTokenizerConfig

_TOKEN_RE = re.compile(
    r"""
    §\s*\d+(?:\.\d+)*
    |\$[A-Za-z][A-Za-z0-9]{0,9}(?:\.[A-Za-z0-9]{1,4})?
    |[+-]?\d+(?:,\d{3})*(?:\.\d+)?%
    |[A-Za-z]{1,10}\.[A-Za-z0-9]{1,4}
    |\d+(?:\.\d+)+
    |[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\+?
    |[A-Za-z]+[A-Za-z0-9]*\+?
    |[+-]?\d+(?:,\d{3})*(?:\.\d+)?
    """,
    flags=re.VERBOSE,
)

_DOMAIN_PROTECTED: dict[Domain, frozenset[str]] = {
    Domain.FINANCIAL: frozenset(
        {
            "10-k",
            "10-q",
            "q1",
            "q2",
            "q3",
            "q4",
            "fy",
            "eps",
            "ebitda",
        }
    ),
    Domain.LEGAL: frozenset({"article", "clause", "msa", "nda", "section"}),
    Domain.RESEARCH: frozenset({"bm25", "bm25+", "eq", "fig", "rrf", "table"}),
}


def _normalize(raw: str, *, lowercase: bool) -> str:
    token = re.sub(r"\s+", "", raw) if raw.startswith("§") else raw
    return token.lower() if lowercase else token


def _plain_alpha(token: str) -> bool:
    return token.isalpha()


class DomainAwareTokenizer:
    """Conservative tokenizer that preserves domain-significant lexical forms."""

    name = "domain-aware-lexical-v1"

    def __init__(self, config: SparseTokenizerConfig | None = None) -> None:
        self.config = config or SparseTokenizerConfig()
        self._stopwords = frozenset(
            word.lower() if self.config.lowercase else word for word in self.config.stopwords
        )

    def tokenize(self, text: str, *, domain: Domain | None = None) -> tuple[str, ...]:
        """Return normalized lexical tokens while retaining domain-specific exact forms."""
        tokens: list[str] = []
        protected = _DOMAIN_PROTECTED.get(domain, frozenset())
        for match in _TOKEN_RE.finditer(text):
            token = _normalize(match.group(0), lowercase=self.config.lowercase)
            if not token:
                continue
            if (
                self.config.remove_stopwords
                and _plain_alpha(token)
                and token in self._stopwords
                and token not in protected
            ):
                continue
            tokens.append(token)
        return tuple(tokens)

    def unique_terms(self, text: str, *, domain: Domain | None = None) -> tuple[str, ...]:
        """Return query terms in first-seen order without duplicates."""
        return tuple(dict.fromkeys(self.tokenize(text, domain=domain)))


def count_terms(tokens: Iterable[str]) -> dict[str, int]:
    """Return a deterministic insertion-ordered term-frequency mapping."""
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts
