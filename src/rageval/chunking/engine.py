"""Common chunking engine for fixed-token, semantic, section-aware, and table-aware output."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from rageval.cleaning.models import CleanedDocument
from rageval.core.ids import fingerprint_mapping, make_chunk_id
from rageval.core.protocols import EmbeddingProvider
from rageval.models.contracts import Chunk, DocumentElement, Domain, ElementType

from rageval.chunking.models import ChunkingConfig, ChunkingResult, ChunkStrategy
from rageval.chunking.tokenizer import (
    Tokenizer,
    WhitespaceTokenizer,
    sentence_segments,
    starts_legal_clause,
)


@dataclass(frozen=True)
class _ElementUnit:
    element: DocumentElement
    tokens: tuple[str, ...]
    source_element_id: str
    section_hint: str | None


@dataclass(frozen=True)
class _TokenRef:
    token: str
    cleaned_element_id: str
    source_element_id: str
    page_number: int | None
    kind: ElementType


@dataclass(frozen=True)
class _SemanticSegment:
    text: str
    tokens: tuple[str, ...]
    unit: _ElementUnit


@dataclass(frozen=True)
class _DraftChunk:
    text: str
    token_count: int
    metadata: dict[str, object]


@runtime_checkable
class SimilarityPolicy(Protocol):
    """Similarity boundary used by the semantic chunker."""

    @property
    def name(self) -> str:
        """Stable policy identifier included in chunk metadata."""
        ...

    def similarity(self, left: Sequence[float], right: Sequence[float]) -> float:
        """Return a deterministic similarity score for two embeddings."""
        ...


class CosineSimilarityPolicy:
    """Cosine similarity with safe zero-vector handling."""

    name = "cosine-v1"

    def similarity(self, left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            raise ValueError("embedding dimensions do not match")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def chunking_config_fingerprint(config: ChunkingConfig) -> str:
    """Return a stable fingerprint for every behavior-affecting chunking option."""
    return fingerprint_mapping(config.model_dump(mode="json"))


def _ordered_unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _source_element_id(element: DocumentElement) -> str:
    value = element.metadata.get("source_element_id")
    return value if isinstance(value, str) else element.element_id


def _section_hint(element: DocumentElement) -> str | None:
    value = element.metadata.get("section_hint")
    return value if isinstance(value, str) and value.strip() else None


def _unit(element: DocumentElement, tokenizer: Tokenizer) -> _ElementUnit:
    return _ElementUnit(
        element=element,
        tokens=tokenizer.tokenize(element.text),
        source_element_id=_source_element_id(element),
        section_hint=_section_hint(element),
    )


def _units_boundary(
    previous: _ElementUnit,
    current: _ElementUnit,
    *,
    domain: Domain,
    config: ChunkingConfig,
) -> bool:
    if (
        config.section_aware
        and previous.section_hint is not None
        and current.section_hint is not None
        and previous.section_hint != current.section_hint
    ):
        return True
    return (
        domain is Domain.LEGAL
        and config.preserve_legal_clauses
        and starts_legal_clause(current.element.text)
    )


def _refs_from_units(units: Sequence[_ElementUnit]) -> list[_TokenRef]:
    refs: list[_TokenRef] = []
    for unit in units:
        refs.extend(
            _TokenRef(
                token=token,
                cleaned_element_id=unit.element.element_id,
                source_element_id=unit.source_element_id,
                page_number=unit.element.page_number,
                kind=unit.element.kind,
            )
            for token in unit.tokens
        )
    return refs


def _metadata_from_refs(
    refs: Sequence[_TokenRef],
    *,
    domain: Domain,
    config: ChunkingConfig,
    tokenizer: Tokenizer,
    overlap_tokens: int,
) -> dict[str, object]:
    cleaned_ids = _ordered_unique([ref.cleaned_element_id for ref in refs])
    source_ids = _ordered_unique([ref.source_element_id for ref in refs])
    pages = sorted({ref.page_number for ref in refs if ref.page_number is not None})
    kinds = {ref.cleaned_element_id: ref.kind.value for ref in refs}
    return {
        "strategy": config.strategy.value,
        "domain": domain.value,
        "tokenizer": tokenizer.name,
        "source_pages": pages,
        "cleaned_element_ids": cleaned_ids,
        "source_element_ids": source_ids,
        "source_element_kinds": kinds,
        "overlap_tokens": overlap_tokens,
        "table_aware": config.table_aware,
        "section_aware": config.section_aware,
    }


def _fixed_block_drafts(
    units: Sequence[_ElementUnit],
    *,
    domain: Domain,
    config: ChunkingConfig,
    tokenizer: Tokenizer,
) -> list[_DraftChunk]:
    refs = _refs_from_units(units)
    if not refs:
        return []

    drafts: list[_DraftChunk] = []
    start = 0
    while start < len(refs):
        end = min(start + config.chunk_size, len(refs))
        window = refs[start:end]
        overlap_tokens = 0 if start == 0 else min(config.overlap, len(window))
        metadata = _metadata_from_refs(
            window,
            domain=domain,
            config=config,
            tokenizer=tokenizer,
            overlap_tokens=overlap_tokens,
        )
        metadata.update(
            {
                "source_token_start": start,
                "source_token_end": end,
                "table_row_group": False,
            }
        )
        tokens = tuple(ref.token for ref in window)
        drafts.append(
            _DraftChunk(
                text=tokenizer.detokenize(tokens),
                token_count=len(tokens),
                metadata=metadata,
            )
        )
        if end == len(refs):
            break
        start = end - config.overlap
    return drafts


def _table_base_metadata(
    unit: _ElementUnit,
    *,
    domain: Domain,
    config: ChunkingConfig,
    tokenizer: Tokenizer,
) -> dict[str, object]:
    metadata = _metadata_from_refs(
        [
            _TokenRef(
                token=token,
                cleaned_element_id=unit.element.element_id,
                source_element_id=unit.source_element_id,
                page_number=unit.element.page_number,
                kind=unit.element.kind,
            )
            for token in unit.tokens
        ],
        domain=domain,
        config=config,
        tokenizer=tokenizer,
        overlap_tokens=0,
    )
    source_offset = unit.element.metadata.get("source_offset")
    bbox = unit.element.metadata.get("bbox")
    table_html = unit.element.metadata.get("table_html")
    metadata.update(
        {
            "table_row_group": True,
            "source_table_id": unit.source_element_id,
            "source_table_html": table_html,
            "source_offset": source_offset,
            "bbox": bbox,
        }
    )
    return metadata


def _table_text(header: str, rows: Sequence[str], *, include_header: bool) -> str:
    parts: list[str] = []
    if include_header and header:
        parts.append(header)
    parts.extend(rows)
    return "\n".join(parts)


def _table_drafts(
    unit: _ElementUnit,
    *,
    domain: Domain,
    config: ChunkingConfig,
    tokenizer: Tokenizer,
) -> list[_DraftChunk]:
    rows = [row.strip() for row in unit.element.text.splitlines() if row.strip()]
    if not rows:
        return []
    full_tokens = tokenizer.tokenize(unit.element.text)
    base = _table_base_metadata(
        unit,
        domain=domain,
        config=config,
        tokenizer=tokenizer,
    )
    if len(full_tokens) <= config.chunk_size or len(rows) == 1:
        metadata = dict(base)
        metadata.update(
            {
                "table_row_start": 0,
                "table_row_end": len(rows),
                "repeated_header": False,
                "oversized_atomic_row": len(full_tokens) > config.chunk_size,
            }
        )
        return [
            _DraftChunk(
                text=unit.element.text,
                token_count=len(full_tokens),
                metadata=metadata,
            )
        ]

    header = rows[0]
    data_rows = list(enumerate(rows[1:], start=1))
    groups: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []

    for row_index, row in data_rows:
        candidate_rows = [value for _, value in [*current, (row_index, row)]]
        candidate_text = _table_text(
            header,
            candidate_rows,
            include_header=config.repeat_table_header,
        )
        candidate_tokens = tokenizer.tokenize(candidate_text)
        if current and len(candidate_tokens) > config.chunk_size:
            groups.append(current)
            current = [(row_index, row)]
        else:
            current.append((row_index, row))
    if current:
        groups.append(current)

    drafts: list[_DraftChunk] = []
    for group_index, group in enumerate(groups):
        group_rows = [value for _, value in group]
        text = _table_text(
            header,
            group_rows,
            include_header=config.repeat_table_header,
        )
        tokens = tokenizer.tokenize(text)
        metadata = dict(base)
        metadata.update(
            {
                "table_row_start": group[0][0],
                "table_row_end": group[-1][0] + 1,
                "repeated_header": group_index > 0 and config.repeat_table_header,
                "header_text": header,
                "oversized_atomic_row": len(tokens) > config.chunk_size and len(group) == 1,
            }
        )
        drafts.append(_DraftChunk(text=text, token_count=len(tokens), metadata=metadata))
    return drafts


def _document_units(document: CleanedDocument, tokenizer: Tokenizer) -> list[_ElementUnit]:
    return [
        _unit(element, tokenizer)
        for element in document.elements
        if element.kind is not ElementType.PAGE_BREAK and element.text.strip()
    ]


class FixedTokenChunker:
    """Fixed-window chunker with section/legal boundaries and table-aware handling."""

    name = "fixed-token"

    def __init__(self, tokenizer: Tokenizer) -> None:
        self.tokenizer = tokenizer

    async def build_drafts(
        self,
        document: CleanedDocument,
        config: ChunkingConfig,
    ) -> list[_DraftChunk]:
        drafts: list[_DraftChunk] = []
        block: list[_ElementUnit] = []

        def flush() -> None:
            if block:
                drafts.extend(
                    _fixed_block_drafts(
                        block,
                        domain=document.document.domain,
                        config=config,
                        tokenizer=self.tokenizer,
                    )
                )
                block.clear()

        for unit in _document_units(document, self.tokenizer):
            if unit.element.kind is ElementType.TABLE and config.table_aware:
                flush()
                drafts.extend(
                    _table_drafts(
                        unit,
                        domain=document.document.domain,
                        config=config,
                        tokenizer=self.tokenizer,
                    )
                )
                continue
            if block and _units_boundary(
                block[-1],
                unit,
                domain=document.document.domain,
                config=config,
            ):
                flush()
            block.append(unit)
        flush()
        return drafts


def _semantic_segments(
    units: Sequence[_ElementUnit],
    *,
    domain: Domain,
    config: ChunkingConfig,
    tokenizer: Tokenizer,
) -> list[_SemanticSegment]:
    segments: list[_SemanticSegment] = []
    for unit in units:
        for text in sentence_segments(
            unit.element.text,
            domain=domain,
            preserve_legal_clause=config.preserve_legal_clauses,
        ):
            tokens = tokenizer.tokenize(text)
            if tokens:
                segments.append(_SemanticSegment(text=text, tokens=tokens, unit=unit))
    return segments


def _semantic_draft(
    segments: Sequence[_SemanticSegment],
    *,
    domain: Domain,
    config: ChunkingConfig,
    tokenizer: Tokenizer,
    policy: SimilarityPolicy,
) -> _DraftChunk:
    refs: list[_TokenRef] = []
    for segment in segments:
        refs.extend(
            _TokenRef(
                token=token,
                cleaned_element_id=segment.unit.element.element_id,
                source_element_id=segment.unit.source_element_id,
                page_number=segment.unit.element.page_number,
                kind=segment.unit.element.kind,
            )
            for token in segment.tokens
        )
    metadata = _metadata_from_refs(
        refs,
        domain=domain,
        config=config,
        tokenizer=tokenizer,
        overlap_tokens=0,
    )
    metadata.update(
        {
            "table_row_group": False,
            "semantic_segment_count": len(segments),
            "similarity_policy": policy.name,
            "oversized_atomic_segment": len(refs) > config.semantic_max_tokens
            and len(segments) == 1,
        }
    )
    return _DraftChunk(
        text=" ".join(segment.text for segment in segments),
        token_count=len(refs),
        metadata=metadata,
    )


class SemanticChunker:
    """Sentence-boundary semantic chunker using an injected embedding provider."""

    name = "semantic"

    def __init__(
        self,
        tokenizer: Tokenizer,
        embedding_provider: EmbeddingProvider,
        similarity_policy: SimilarityPolicy,
    ) -> None:
        self.tokenizer = tokenizer
        self.embedding_provider = embedding_provider
        self.similarity_policy = similarity_policy

    async def _block_drafts(
        self,
        units: Sequence[_ElementUnit],
        *,
        domain: Domain,
        config: ChunkingConfig,
    ) -> list[_DraftChunk]:
        segments = _semantic_segments(
            units,
            domain=domain,
            config=config,
            tokenizer=self.tokenizer,
        )
        if not segments:
            return []
        embeddings = await self.embedding_provider.embed([segment.text for segment in segments])
        if len(embeddings) != len(segments):
            raise ValueError("embedding provider returned the wrong number of vectors")

        groups: list[list[_SemanticSegment]] = []
        current: list[_SemanticSegment] = []
        current_tokens = 0

        for index, segment in enumerate(segments):
            if not current:
                current = [segment]
                current_tokens = len(segment.tokens)
                continue

            similarity = self.similarity_policy.similarity(
                embeddings[index - 1],
                embeddings[index],
            )
            next_total = current_tokens + len(segment.tokens)
            split_for_size = next_total > config.semantic_max_tokens
            split_for_similarity = (
                similarity < config.semantic_similarity_threshold
                and current_tokens >= config.semantic_min_tokens
            )
            if split_for_size or split_for_similarity:
                groups.append(current)
                current = [segment]
                current_tokens = len(segment.tokens)
            else:
                current.append(segment)
                current_tokens = next_total

        if current:
            groups.append(current)
        return [
            _semantic_draft(
                group,
                domain=domain,
                config=config,
                tokenizer=self.tokenizer,
                policy=self.similarity_policy,
            )
            for group in groups
        ]

    async def build_drafts(
        self,
        document: CleanedDocument,
        config: ChunkingConfig,
    ) -> list[_DraftChunk]:
        drafts: list[_DraftChunk] = []
        block: list[_ElementUnit] = []

        async def flush() -> None:
            if block:
                drafts.extend(
                    await self._block_drafts(
                        block,
                        domain=document.document.domain,
                        config=config,
                    )
                )
                block.clear()

        for unit in _document_units(document, self.tokenizer):
            if unit.element.kind is ElementType.TABLE and config.table_aware:
                await flush()
                drafts.extend(
                    _table_drafts(
                        unit,
                        domain=document.document.domain,
                        config=config,
                        tokenizer=self.tokenizer,
                    )
                )
                continue
            if block and _units_boundary(
                block[-1],
                unit,
                domain=document.document.domain,
                config=config,
            ):
                await flush()
            block.append(unit)
        await flush()
        return drafts


class ChunkingEngine:
    """Dispatch all reference strategies through one stable chunking boundary."""

    def __init__(
        self,
        *,
        tokenizer: Tokenizer | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        similarity_policy: SimilarityPolicy | None = None,
    ) -> None:
        self.tokenizer = tokenizer or WhitespaceTokenizer()
        self.embedding_provider = embedding_provider
        self.similarity_policy = similarity_policy or CosineSimilarityPolicy()

    async def chunk(
        self,
        document: CleanedDocument,
        *,
        config: ChunkingConfig,
    ) -> ChunkingResult:
        if config.tokenizer_name != self.tokenizer.name:
            raise ValueError(
                f"config tokenizer {config.tokenizer_name!r} does not match {self.tokenizer.name!r}"
            )
        fingerprint = chunking_config_fingerprint(config)
        if config.strategy is ChunkStrategy.SEMANTIC:
            if self.embedding_provider is None:
                raise ValueError("semantic chunking requires an embedding provider")
            component = SemanticChunker(
                self.tokenizer,
                self.embedding_provider,
                self.similarity_policy,
            )
            drafts = await component.build_drafts(document, config)
        else:
            drafts = await FixedTokenChunker(self.tokenizer).build_drafts(document, config)

        chunks = tuple(
            Chunk(
                chunk_id=make_chunk_id(
                    document_id=document.document.document_id,
                    ordinal=ordinal,
                    config_fingerprint=fingerprint,
                    text=draft.text,
                ),
                document_id=document.document.document_id,
                ordinal=ordinal,
                text=draft.text,
                token_count=draft.token_count,
                config_fingerprint=fingerprint,
                metadata={
                    **draft.metadata,
                    "chunking_config_fingerprint": fingerprint,
                    "source_cleaning_config_fingerprint": document.cleaning_config_fingerprint,
                },
            )
            for ordinal, draft in enumerate(drafts)
        )
        metadata: dict[str, object] = {
            "source_cleaning_config_fingerprint": document.cleaning_config_fingerprint,
            "chunker_version": config.chunker_version,
            "tokenizer": self.tokenizer.name,
        }
        if config.strategy is ChunkStrategy.SEMANTIC and self.embedding_provider is not None:
            metadata["embedding_provider"] = self.embedding_provider.name
            metadata["similarity_policy"] = self.similarity_policy.name
        return ChunkingResult(
            document=document.document,
            config=config,
            config_fingerprint=fingerprint,
            chunks=chunks,
            metadata=metadata,
        )


async def chunk_document(
    document: CleanedDocument,
    *,
    config: ChunkingConfig,
    tokenizer: Tokenizer | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    similarity_policy: SimilarityPolicy | None = None,
) -> ChunkingResult:
    """Convenience entry point for the common Phase 5 chunking interface."""
    engine = ChunkingEngine(
        tokenizer=tokenizer,
        embedding_provider=embedding_provider,
        similarity_policy=similarity_policy,
    )
    return await engine.chunk(document, config=config)
