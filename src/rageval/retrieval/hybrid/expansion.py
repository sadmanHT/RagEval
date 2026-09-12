"""Query-expansion interfaces and deterministic fixtures for hybrid retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from rageval.retrieval.hybrid.models import QueryExpansionConfig


@runtime_checkable
class QueryExpansionProvider(Protocol):
    """Provider boundary for optional local or hosted query expansion."""

    name: str

    async def expand(self, query: str, *, max_expansions: int) -> Sequence[str]:
        """Return terminology additions without removing or rewriting the original query."""
        ...


class DictionaryQueryExpansionProvider:
    """Deterministic phrase-to-terminology expansion used by tests and local evidence."""

    name = "dictionary-expansion-v1"

    def __init__(self, rules: Mapping[str, Sequence[str]]) -> None:
        self._rules = {
            key.strip().casefold(): tuple(value.strip() for value in values if value.strip())
            for key, values in rules.items()
            if key.strip()
        }

    async def expand(self, query: str, *, max_expansions: int) -> tuple[str, ...]:
        if max_expansions <= 0:
            return ()
        normalized = query.casefold()
        output: list[str] = []
        seen: set[str] = set()
        for key in sorted(self._rules):
            if key not in normalized:
                continue
            for expansion in self._rules[key]:
                identity = expansion.casefold()
                if identity in seen or identity == normalized:
                    continue
                seen.add(identity)
                output.append(expansion)
                if len(output) >= max_expansions:
                    return tuple(output)
        return tuple(output)


def bound_expansions(
    query: str,
    expansions: Sequence[str],
    config: QueryExpansionConfig,
) -> tuple[str, ...]:
    """Normalize provider output while enforcing count/length/original-query invariants."""
    if not config.enabled or config.max_expansions == 0:
        return ()
    original = query.strip().casefold()
    bounded: list[str] = []
    seen: set[str] = {original}
    for candidate in expansions:
        normalized = " ".join(candidate.split())
        if not normalized:
            continue
        normalized = normalized[: config.max_expansion_chars].rstrip()
        identity = normalized.casefold()
        if not normalized or identity in seen:
            continue
        seen.add(identity)
        bounded.append(normalized)
        if len(bounded) >= config.max_expansions:
            break
    return tuple(bounded)


def assemble_retrieval_query(query: str, expansions: Sequence[str]) -> str:
    """Build the retrieval query while always preserving the user's original query verbatim."""
    original = " ".join(query.split())
    if not original:
        raise ValueError("query must not be blank")
    if not expansions:
        return original
    return " ".join((original, *expansions))
