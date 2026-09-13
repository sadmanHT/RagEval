"""Deterministic context assembly with token budgets and near-duplicate suppression."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from rageval.chunking.tokenizer import Tokenizer, WhitespaceTokenizer
from rageval.core.ids import fingerprint_mapping
from rageval.generation.models import AssembledContext, ContextAssemblyConfig, ContextChunk
from rageval.models.contracts import RerankResult

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_SOURCE_METADATA_KEYS = (
    "domain",
    "source_pages",
    "source_element_ids",
    "cleaned_element_ids",
    "source_uri",
    "source_table_id",
    "table_row_start",
    "table_row_end",
    "source_date",
)
_SEPARATOR = "\n\n---\n\n"


def context_config_fingerprint(config: ContextAssemblyConfig) -> str:
    """Fingerprint every context-assembly behavior that can affect prompts."""
    return fingerprint_mapping(config.model_dump(mode="json"))


def _normalized_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _token_set(text: str) -> set[str]:
    return set(_WORD_RE.findall(_normalized_text(text)))


def _is_near_duplicate(left: str, right: str, threshold: float) -> bool:
    left_normalized = _normalized_text(left)
    right_normalized = _normalized_text(right)
    if left_normalized == right_normalized:
        return True
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return False
    union = left_tokens | right_tokens
    if not union:
        return False
    return len(left_tokens & right_tokens) / len(union) >= threshold


def _source_metadata(result: RerankResult) -> dict[str, object]:
    metadata = result.retrieval.chunk.metadata
    return {key: metadata[key] for key in _SOURCE_METADATA_KEYS if key in metadata}


def _render_block(chunk: ContextChunk) -> str:
    source = json.dumps(
        chunk.source_metadata,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    truncated = "true" if chunk.truncated else "false"
    return (
        f'[CONTEXT_CHUNK id="{chunk.chunk_id}" rank="{chunk.rank}" '
        f'document_id="{chunk.document_id}" truncated="{truncated}"]\n'
        f"SOURCE_METADATA: {source}\n"
        "CONTENT:\n"
        f"{chunk.text}\n"
        "[/CONTEXT_CHUNK]"
    )


class ContextAssembler:
    """Build a deterministic, bounded prompt context from reranked retrieval results."""

    def __init__(
        self,
        *,
        config: ContextAssemblyConfig | None = None,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        self.config = config or ContextAssemblyConfig()
        self.tokenizer = tokenizer or WhitespaceTokenizer()
        if self.config.tokenizer_name != self.tokenizer.name:
            raise ValueError(
                "context config tokenizer_name does not match the supplied tokenizer: "
                f"{self.config.tokenizer_name!r} != {self.tokenizer.name!r}"
            )
        self.config_fingerprint = context_config_fingerprint(self.config)

    def _candidate(self, result: RerankResult, *, text: str, truncated: bool) -> ContextChunk:
        chunk = result.retrieval.chunk
        tokens = self.tokenizer.tokenize(text)
        return ContextChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            rank=result.rank,
            text=text,
            token_count=len(tokens),
            source_metadata=_source_metadata(result),
            truncated=truncated,
        )

    def _rendered_token_count(self, chunks: Sequence[ContextChunk]) -> int:
        rendered = _SEPARATOR.join(_render_block(chunk) for chunk in chunks)
        return len(self.tokenizer.tokenize(rendered))

    def _truncate_to_budget(
        self,
        result: RerankResult,
        accepted: Sequence[ContextChunk],
    ) -> ContextChunk | None:
        source_tokens = self.tokenizer.tokenize(result.retrieval.chunk.text)
        if len(source_tokens) < self.config.min_truncated_chunk_tokens:
            return None
        low = self.config.min_truncated_chunk_tokens
        high = len(source_tokens)
        best: ContextChunk | None = None
        while low <= high:
            middle = (low + high) // 2
            text = self.tokenizer.detokenize(source_tokens[:middle])
            candidate = self._candidate(result, text=text, truncated=True)
            if self._rendered_token_count((*accepted, candidate)) <= self.config.max_context_tokens:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best

    def assemble(self, results: Sequence[RerankResult]) -> AssembledContext:
        """Order, de-duplicate, and fit reranked chunks into the configured token budget."""
        ordered = sorted(
            results,
            key=lambda item: (
                item.rank,
                item.retrieval.rank,
                item.retrieval.chunk.chunk_id,
            ),
        )
        unique: list[RerankResult] = []
        duplicate_ids: list[str] = []
        for result in ordered:
            text = result.retrieval.chunk.text
            if any(
                _is_near_duplicate(
                    text,
                    existing.retrieval.chunk.text,
                    self.config.near_duplicate_jaccard_threshold,
                )
                for existing in unique
            ):
                duplicate_ids.append(result.retrieval.chunk.chunk_id)
                continue
            unique.append(result)

        accepted: list[ContextChunk] = []
        omitted_ids: list[str] = []
        for index, result in enumerate(unique):
            candidate = self._candidate(
                result,
                text=result.retrieval.chunk.text,
                truncated=False,
            )
            if self._rendered_token_count((*accepted, candidate)) <= self.config.max_context_tokens:
                accepted.append(candidate)
                continue

            truncated = self._truncate_to_budget(result, accepted)
            if truncated is not None:
                accepted.append(truncated)
            else:
                omitted_ids.append(result.retrieval.chunk.chunk_id)
            omitted_ids.extend(
                later.retrieval.chunk.chunk_id for later in unique[index + 1 :]
            )
            break

        rendered = _SEPARATOR.join(_render_block(chunk) for chunk in accepted)
        token_count = len(self.tokenizer.tokenize(rendered))
        if token_count > self.config.max_context_tokens:
            raise RuntimeError("context assembler exceeded configured token budget")
        return AssembledContext(
            rendered=rendered,
            chunks=tuple(accepted),
            included_chunk_ids=tuple(chunk.chunk_id for chunk in accepted),
            omitted_chunk_ids=tuple(omitted_ids),
            duplicate_chunk_ids=tuple(duplicate_ids),
            token_count=token_count,
            config_fingerprint=self.config_fingerprint,
        )
