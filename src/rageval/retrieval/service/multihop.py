"""Bounded, diagnosable multi-hop planning for cross-section references."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from rageval.retrieval.hybrid.models import HybridSearchResponse

_REFERENCE_RE = re.compile(
    r"\b(?:section|clause|appendix|schedule)\s+[A-Za-z0-9][A-Za-z0-9.\-]*",
    flags=re.IGNORECASE,
)
_RELATION_CUES = (
    "how ",
    "why ",
    "affect",
    "relationship",
    "compare",
    "based on",
    "according to",
    "under ",
)


@runtime_checkable
class MultiHopPlanner(Protocol):
    """Decide whether to multi-hop and derive bounded second-hop queries."""

    async def should_multi_hop(self, query: str, first_hop: HybridSearchResponse) -> bool: ...

    async def derive_queries(
        self,
        query: str,
        first_hop: HybridSearchResponse,
        *,
        max_queries: int,
    ) -> tuple[str, ...]: ...


class ReferenceAwareMultiHopPlanner:
    """Conservative local rule planner based on explicit cross-section references."""

    async def should_multi_hop(self, query: str, first_hop: HybridSearchResponse) -> bool:
        normalized = query.casefold()
        if not any(cue in normalized for cue in _RELATION_CUES):
            return False
        return bool(await self.derive_queries(query, first_hop, max_queries=1))

    async def derive_queries(
        self,
        query: str,
        first_hop: HybridSearchResponse,
        *,
        max_queries: int,
    ) -> tuple[str, ...]:
        if max_queries < 1:
            return ()
        seen: set[str] = set()
        derived: list[str] = []
        for result in first_hop.results:
            for match in _REFERENCE_RE.finditer(result.chunk.text):
                candidate = " ".join(match.group(0).split())
                key = candidate.casefold()
                if key in seen:
                    continue
                seen.add(key)
                derived.append(candidate)
                if len(derived) >= max_queries:
                    return tuple(derived)
        return tuple(derived)
