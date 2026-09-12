"""Deterministic BM25/BM25+ indexing, persistence, filtering, and retrieval."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from rageval.core.errors import IndexingError
from rageval.core.ids import fingerprint_mapping
from rageval.models.contracts import RetrievalResult
from rageval.retrieval.sparse.models import (
    BM25Variant,
    SparseDocumentInput,
    SparseIndexConfig,
    SparseIndexEntry,
    SparseIndexSnapshot,
    SparseMatchDiagnostic,
    SparseSearchFilter,
    SparseSearchResponse,
)
from rageval.retrieval.sparse.tokenizer import DomainAwareTokenizer, count_terms


def sparse_config_fingerprint(config: SparseIndexConfig) -> str:
    """Return a stable fingerprint for every sparse-index behavior option."""
    return fingerprint_mapping(config.model_dump(mode="json"))


def _statistics(entries: Sequence[SparseIndexEntry]) -> tuple[dict[str, int], float]:
    document_frequencies: dict[str, int] = {}
    total_length = 0
    for entry in entries:
        total_length += entry.document_length
        for term in sorted(set(entry.tokens)):
            document_frequencies[term] = document_frequencies.get(term, 0) + 1
    average_length = total_length / len(entries) if entries else 0.0
    return dict(sorted(document_frequencies.items())), average_length


def _index_fingerprint(
    config_fingerprint: str,
    entries: Sequence[SparseIndexEntry],
) -> str:
    payload: dict[str, object] = {
        "config_fingerprint": config_fingerprint,
        "entries": [
            {
                "chunk": entry.chunk.model_dump(mode="json"),
                "domain": entry.domain.value,
                "source_date": entry.source_date.isoformat() if entry.source_date else None,
                "tokens": list(entry.tokens),
            }
            for entry in entries
        ],
    }
    return fingerprint_mapping(payload)


def _matches_filter(entry: SparseIndexEntry, filters: SparseSearchFilter) -> bool:
    if filters.domain is not None and entry.domain is not filters.domain:
        return False
    if filters.document_id is not None and entry.chunk.document_id != filters.document_id:
        return False
    if (
        filters.chunking_config_fingerprint is not None
        and entry.chunk.config_fingerprint != filters.chunking_config_fingerprint
    ):
        return False
    if filters.date_from is not None:
        if entry.source_date is None or entry.source_date < filters.date_from:
            return False
    if filters.date_to is not None:
        if entry.source_date is None or entry.source_date > filters.date_to:
            return False
    return True


class BM25SparseIndex:
    """Immutable deterministic sparse index over canonical Phase 5 chunks."""

    def __init__(
        self,
        snapshot: SparseIndexSnapshot,
        *,
        tokenizer: DomainAwareTokenizer | None = None,
    ) -> None:
        expected_config_fingerprint = sparse_config_fingerprint(snapshot.config)
        if snapshot.config_fingerprint != expected_config_fingerprint:
            raise IndexingError("sparse snapshot config fingerprint does not match its configuration")
        expected_index_fingerprint = _index_fingerprint(
            snapshot.config_fingerprint,
            snapshot.entries,
        )
        if snapshot.index_fingerprint != expected_index_fingerprint:
            raise IndexingError("sparse snapshot index fingerprint does not match its entries")
        frequencies, average_length = _statistics(snapshot.entries)
        if frequencies != snapshot.document_frequencies:
            raise IndexingError("sparse snapshot document frequencies are inconsistent")
        if not math.isclose(average_length, snapshot.average_document_length, abs_tol=1e-12):
            raise IndexingError("sparse snapshot average document length is inconsistent")
        if len(snapshot.entries) != snapshot.document_count:
            raise IndexingError("sparse snapshot document count is inconsistent")

        active_tokenizer = tokenizer or DomainAwareTokenizer(snapshot.config.tokenizer)
        if active_tokenizer.config != snapshot.config.tokenizer:
            raise ValueError("tokenizer configuration must match the sparse snapshot configuration")
        self.snapshot = snapshot
        self.config = snapshot.config
        self.tokenizer = active_tokenizer
        self.name = f"sparse-{self.config.variant.value}"

    @classmethod
    def build(
        cls,
        documents: Sequence[SparseDocumentInput],
        *,
        config: SparseIndexConfig | None = None,
        tokenizer: DomainAwareTokenizer | None = None,
    ) -> BM25SparseIndex:
        """Build a deterministic index independent of input document/chunk ordering."""
        active_config = config or SparseIndexConfig()
        active_tokenizer = tokenizer or DomainAwareTokenizer(active_config.tokenizer)
        if active_tokenizer.config != active_config.tokenizer:
            raise ValueError("tokenizer configuration must match SparseIndexConfig.tokenizer")

        entries: list[SparseIndexEntry] = []
        seen_chunk_ids: set[str] = set()
        ordered_documents = sorted(documents, key=lambda item: item.document.document_id)
        for item in ordered_documents:
            ordered_chunks = sorted(item.chunks, key=lambda chunk: (chunk.ordinal, chunk.chunk_id))
            for chunk in ordered_chunks:
                if chunk.document_id != item.document.document_id:
                    raise IndexingError("all sparse chunks must belong to their supplied document")
                if chunk.chunk_id in seen_chunk_ids:
                    raise IndexingError(f"duplicate chunk ID in sparse corpus: {chunk.chunk_id}")
                seen_chunk_ids.add(chunk.chunk_id)
                tokens = active_tokenizer.tokenize(chunk.text, domain=item.document.domain)
                entries.append(
                    SparseIndexEntry(
                        chunk=chunk,
                        domain=item.document.domain,
                        source_date=item.source_date,
                        tokens=tokens,
                        term_frequencies=count_terms(tokens),
                        document_length=len(tokens),
                    )
                )

        entries.sort(key=lambda entry: entry.chunk.chunk_id)
        frequencies, average_length = _statistics(entries)
        config_fingerprint = sparse_config_fingerprint(active_config)
        snapshot = SparseIndexSnapshot(
            config=active_config,
            config_fingerprint=config_fingerprint,
            index_fingerprint=_index_fingerprint(config_fingerprint, entries),
            entries=tuple(entries),
            document_frequencies=frequencies,
            average_document_length=average_length,
            document_count=len(entries),
        )
        return cls(snapshot, tokenizer=active_tokenizer)

    def save(self, path: str | Path) -> None:
        """Persist the complete deterministic sparse snapshot as canonical JSON."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.snapshot.model_dump(mode="json")
        target.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> BM25SparseIndex:
        """Load and integrity-check a persisted sparse snapshot."""
        snapshot = SparseIndexSnapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))
        return cls(snapshot)

    def count(self, filters: SparseSearchFilter | None = None) -> int:
        """Count indexed chunks matching optional metadata filters."""
        active_filters = filters or SparseSearchFilter()
        return sum(1 for entry in self.snapshot.entries if _matches_filter(entry, active_filters))

    def _idf(self, term: str) -> float:
        document_frequency = self.snapshot.document_frequencies.get(term, 0)
        if document_frequency == 0 or self.snapshot.document_count == 0:
            return 0.0
        numerator = self.snapshot.document_count - document_frequency + 0.5
        denominator = document_frequency + 0.5
        return math.log1p(numerator / denominator)

    def _score(self, entry: SparseIndexEntry, query_counts: dict[str, int]) -> float:
        if not query_counts or not entry.term_frequencies:
            return 0.0
        average_length = self.snapshot.average_document_length or 1.0
        length_ratio = entry.document_length / average_length
        length_norm = self.config.k1 * (1.0 - self.config.b + self.config.b * length_ratio)
        score = 0.0
        for term, query_frequency in query_counts.items():
            term_frequency = entry.term_frequencies.get(term, 0)
            if term_frequency <= 0:
                continue
            saturation = (term_frequency * (self.config.k1 + 1.0)) / (
                term_frequency + length_norm
            )
            if self.config.variant is BM25Variant.BM25_PLUS:
                saturation += self.config.delta
            score += self._idf(term) * saturation * query_frequency
        return score

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 20,
    ) -> tuple[RetrievalResult, ...]:
        """Common retriever-interface projection returning canonical results only."""
        response = await self.search(query, top_k=top_k)
        return response.results

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SparseSearchFilter | None = None,
    ) -> SparseSearchResponse:
        """Score eligible chunks and return stable BM25/BM25+ lexical results."""
        active_top_k = self.config.default_top_k if top_k is None else top_k
        if active_top_k < 1:
            raise ValueError("top_k must be positive")
        active_filters = filters or SparseSearchFilter()
        start = time.perf_counter()
        query_tokens = self.tokenizer.tokenize(query, domain=active_filters.domain)
        query_counts = count_terms(query_tokens)

        scored: list[tuple[float, SparseIndexEntry, tuple[str, ...]]] = []
        if query_counts:
            for entry in self.snapshot.entries:
                if not _matches_filter(entry, active_filters):
                    continue
                matched_terms = tuple(
                    dict.fromkeys(
                        term for term in query_tokens if entry.term_frequencies.get(term, 0) > 0
                    )
                )
                if not matched_terms:
                    continue
                score = self._score(entry, query_counts)
                if score > 0.0:
                    scored.append((score, entry, matched_terms))
        scored.sort(key=lambda item: (-item[0], item[1].chunk.chunk_id))
        selected = scored[:active_top_k]

        results: list[RetrievalResult] = []
        diagnostics: list[SparseMatchDiagnostic] = []
        for rank, (score, entry, matched_terms) in enumerate(selected, start=1):
            matched_frequencies = {
                term: entry.term_frequencies[term]
                for term in matched_terms
                if term in entry.term_frequencies
            }
            metadata: dict[str, object] = {
                "index_version": self.config.index_version,
                "index_fingerprint": self.snapshot.index_fingerprint,
                "sparse_config_fingerprint": self.snapshot.config_fingerprint,
                "variant": self.config.variant.value,
                "domain": entry.domain.value,
                "source_date": entry.source_date.isoformat() if entry.source_date else None,
                "chunking_config_fingerprint": entry.chunk.config_fingerprint,
                "query_tokens": list(query_tokens),
                "matched_terms": list(matched_terms),
            }
            results.append(
                RetrievalResult(
                    chunk=entry.chunk,
                    score=score,
                    rank=rank,
                    retriever=self.name,
                    metadata=metadata,
                )
            )
            diagnostics.append(
                SparseMatchDiagnostic(
                    chunk_id=entry.chunk.chunk_id,
                    rank=rank,
                    score=score,
                    matched_terms=matched_terms,
                    term_frequencies=matched_frequencies,
                )
            )

        return SparseSearchResponse(
            query=query,
            query_tokens=query_tokens,
            results=tuple(results),
            diagnostics=tuple(diagnostics),
            index_fingerprint=self.snapshot.index_fingerprint,
            config_fingerprint=self.snapshot.config_fingerprint,
            index_version=self.config.index_version,
            variant=self.config.variant,
            total_latency_ms=(time.perf_counter() - start) * 1000.0,
            filters=active_filters,
        )
