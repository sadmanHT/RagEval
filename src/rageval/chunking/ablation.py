"""Measured chunking ablation harness for deterministic fixture and corpus runs."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from rageval.cleaning.models import CleanedDocument
from rageval.core.ids import fingerprint_mapping
from rageval.core.protocols import EmbeddingProvider
from rageval.models.contracts import Chunk, Domain, ElementType

from rageval.chunking.engine import ChunkingEngine, SimilarityPolicy
from rageval.chunking.models import (
    AblationReport,
    ChunkingConfig,
    ChunkingResult,
    ChunkingStats,
    TokenLengthStats,
)
from rageval.chunking.tokenizer import Tokenizer


def _percentile(values: Sequence[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return float(ordered[rank - 1])


def _token_stats(chunks: Sequence[Chunk]) -> TokenLengthStats:
    lengths = [chunk.token_count for chunk in chunks]
    if not lengths:
        return TokenLengthStats(count=0, minimum=0, maximum=0, mean=0.0, p50=0.0, p95=0.0)
    return TokenLengthStats(
        count=len(lengths),
        minimum=min(lengths),
        maximum=max(lengths),
        mean=sum(lengths) / len(lengths),
        p50=_percentile(lengths, 0.50),
        p95=_percentile(lengths, 0.95),
    )


def _mean_overlap(chunks: Sequence[Chunk]) -> float:
    if not chunks:
        return 0.0
    overlaps: list[int] = []
    for chunk in chunks:
        value = chunk.metadata.get("overlap_tokens")
        overlaps.append(value if isinstance(value, int) else 0)
    return sum(overlaps) / len(overlaps)


def _provenance_coverage(
    documents: Sequence[CleanedDocument],
    results: Sequence[ChunkingResult],
) -> float:
    expected = {
        (document.document.document_id, element.element_id)
        for document in documents
        for element in document.elements
        if element.kind is not ElementType.PAGE_BREAK and element.text.strip()
    }
    if not expected:
        return 1.0

    covered: set[tuple[str, str]] = set()
    for result in results:
        for chunk in result.chunks:
            raw_ids = chunk.metadata.get("cleaned_element_ids")
            if not isinstance(raw_ids, list):
                continue
            for element_id in raw_ids:
                if isinstance(element_id, str):
                    covered.add((result.document.document_id, element_id))
    return len(expected & covered) / len(expected)


def _table_fragmentation_count(
    documents: Sequence[CleanedDocument],
    results: Sequence[ChunkingResult],
) -> int:
    tables = {
        (document.document.document_id, element.element_id)
        for document in documents
        for element in document.elements
        if element.kind is ElementType.TABLE
    }
    chunk_hits: dict[tuple[str, str], list[Chunk]] = defaultdict(list)
    for result in results:
        for chunk in result.chunks:
            raw_ids = chunk.metadata.get("cleaned_element_ids")
            if not isinstance(raw_ids, list):
                continue
            for element_id in raw_ids:
                if isinstance(element_id, str):
                    key = (result.document.document_id, element_id)
                    if key in tables:
                        chunk_hits[key].append(chunk)

    fragmented = 0
    for table in tables:
        hits = chunk_hits.get(table, [])
        if len(hits) <= 1:
            continue
        if any(chunk.metadata.get("table_row_group") is not True for chunk in hits):
            fragmented += 1
    return fragmented


def _dataset_fingerprint(documents: Sequence[CleanedDocument]) -> str:
    values: dict[str, object] = {}
    for document in sorted(documents, key=lambda item: item.document.document_id):
        values[document.document.document_id] = {
            "checksum": document.document.checksum_sha256,
            "cleaning_config_fingerprint": document.cleaning_config_fingerprint,
            "element_ids": [element.element_id for element in document.elements],
        }
    return fingerprint_mapping(values)


async def run_chunking_ablation(
    documents: Sequence[CleanedDocument],
    *,
    configs: Sequence[ChunkingConfig],
    embedding_provider: EmbeddingProvider | None = None,
    tokenizer: Tokenizer | None = None,
    similarity_policy: SimilarityPolicy | None = None,
    metadata: dict[str, object] | None = None,
) -> AblationReport:
    """Run every supplied configuration and return measured per-domain statistics."""
    ordered_documents = sorted(documents, key=lambda item: item.document.document_id)
    stats: list[ChunkingStats] = []

    for config in configs:
        engine = ChunkingEngine(
            tokenizer=tokenizer,
            embedding_provider=embedding_provider,
            similarity_policy=similarity_policy,
        )
        results = [await engine.chunk(document, config=config) for document in ordered_documents]
        for domain in Domain:
            domain_documents = [
                document for document in ordered_documents if document.document.domain is domain
            ]
            domain_results = [result for result in results if result.document.domain is domain]
            chunks = [chunk for result in domain_results for chunk in result.chunks]
            stats.append(
                ChunkingStats(
                    strategy=config.strategy,
                    domain=domain,
                    document_count=len(domain_documents),
                    chunk_count=len(chunks),
                    token_lengths=_token_stats(chunks),
                    mean_overlap_tokens=_mean_overlap(chunks),
                    table_fragmentation_count=_table_fragmentation_count(
                        domain_documents,
                        domain_results,
                    ),
                    provenance_coverage=_provenance_coverage(
                        domain_documents,
                        domain_results,
                    ),
                )
            )

    return AblationReport(
        dataset_fingerprint=_dataset_fingerprint(ordered_documents),
        configs=tuple(configs),
        stats=tuple(stats),
        metadata=metadata or {},
    )
