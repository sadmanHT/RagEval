"""Deterministic Reciprocal Rank Fusion over canonical retrieval results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rageval.core.errors import RetrievalError
from rageval.models.contracts import Chunk, RetrievalResult
from rageval.retrieval.hybrid.models import FusionContribution, HybridResultDiagnostic


@dataclass(frozen=True)
class _BranchHit:
    result: RetrievalResult
    contribution: float


@dataclass
class _Accumulator:
    chunk: Chunk
    dense: _BranchHit | None = None
    sparse: _BranchHit | None = None

    @property
    def score(self) -> float:
        return (self.dense.contribution if self.dense else 0.0) + (
            self.sparse.contribution if self.sparse else 0.0
        )

    @property
    def best_rank(self) -> int:
        ranks = [hit.result.rank for hit in (self.dense, self.sparse) if hit is not None]
        return min(ranks)


def _dedupe_branch(results: Sequence[RetrievalResult]) -> tuple[RetrievalResult, ...]:
    """Keep one best-ranked result per chunk so a branch cannot double-count a chunk."""
    selected: dict[str, RetrievalResult] = {}
    for result in results:
        current = selected.get(result.chunk.chunk_id)
        if current is None or (result.rank, -result.score) < (current.rank, -current.score):
            selected[result.chunk.chunk_id] = result
    return tuple(sorted(selected.values(), key=lambda item: (item.rank, item.chunk.chunk_id)))


def fuse_rrf(
    dense_results: Sequence[RetrievalResult],
    sparse_results: Sequence[RetrievalResult],
    *,
    rrf_k: int = 60,
    top_k: int = 20,
) -> tuple[tuple[RetrievalResult, ...], tuple[HybridResultDiagnostic, ...]]:
    """Fuse 1-based dense/sparse rankings with ``1 / (rrf_k + rank)`` semantics."""
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if top_k < 1:
        raise ValueError("top_k must be positive")

    accumulators: dict[str, _Accumulator] = {}
    for branch, results in (
        ("dense", _dedupe_branch(dense_results)),
        ("sparse", _dedupe_branch(sparse_results)),
    ):
        for result in results:
            contribution = 1.0 / (rrf_k + result.rank)
            chunk_id = result.chunk.chunk_id
            accumulator = accumulators.get(chunk_id)
            if accumulator is None:
                accumulator = _Accumulator(chunk=result.chunk)
                accumulators[chunk_id] = accumulator
            elif accumulator.chunk != result.chunk:
                raise RetrievalError(
                    f"chunk identity collision for {chunk_id}: "
                    "branches disagree on canonical payload"
                )
            hit = _BranchHit(result=result, contribution=contribution)
            if branch == "dense":
                accumulator.dense = hit
            else:
                accumulator.sparse = hit

    ordered = sorted(
        accumulators.items(),
        key=lambda item: (-item[1].score, item[1].best_rank, item[0]),
    )[:top_k]
    fused_results: list[RetrievalResult] = []
    diagnostics: list[HybridResultDiagnostic] = []
    for final_rank, (chunk_id, accumulator) in enumerate(ordered, start=1):
        dense = accumulator.dense
        sparse = accumulator.sparse
        contributions: list[FusionContribution] = []
        if dense is not None:
            contributions.append(
                FusionContribution(
                    branch="dense",
                    source_rank=dense.result.rank,
                    source_score=dense.result.score,
                    rrf_contribution=dense.contribution,
                )
            )
        if sparse is not None:
            contributions.append(
                FusionContribution(
                    branch="sparse",
                    source_rank=sparse.result.rank,
                    source_score=sparse.result.score,
                    rrf_contribution=sparse.contribution,
                )
            )
        metadata: dict[str, object] = {
            "rrf_k": rrf_k,
            "dense_rank": dense.result.rank if dense else None,
            "sparse_rank": sparse.result.rank if sparse else None,
            "dense_score": dense.result.score if dense else None,
            "sparse_score": sparse.result.score if sparse else None,
            "dense_rrf_contribution": dense.contribution if dense else 0.0,
            "sparse_rrf_contribution": sparse.contribution if sparse else 0.0,
            "dense_metadata": dense.result.metadata if dense else None,
            "sparse_metadata": sparse.result.metadata if sparse else None,
        }
        fused_results.append(
            RetrievalResult(
                chunk=accumulator.chunk,
                score=accumulator.score,
                rank=final_rank,
                retriever="hybrid-rrf",
                metadata=metadata,
            )
        )
        diagnostics.append(
            HybridResultDiagnostic(
                chunk_id=chunk_id,
                final_rank=final_rank,
                rrf_score=accumulator.score,
                dense_rank=dense.result.rank if dense else None,
                sparse_rank=sparse.result.rank if sparse else None,
                dense_score=dense.result.score if dense else None,
                sparse_score=sparse.result.score if sparse else None,
                dense_rrf_contribution=dense.contribution if dense else 0.0,
                sparse_rrf_contribution=sparse.contribution if sparse else 0.0,
                contributions=tuple(contributions),
            )
        )
    return tuple(fused_results), tuple(diagnostics)
