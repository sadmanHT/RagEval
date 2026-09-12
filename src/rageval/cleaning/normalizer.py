"""Deterministic text normalization and similarity helpers."""

from __future__ import annotations

import re
import unicodedata

from rageval.cleaning.models import CleaningConfig
from rageval.core.ids import fingerprint_mapping
from rageval.models.contracts import ElementType

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ZERO_WIDTH_ARTIFACTS = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff]")
_HYPHENATED_LINEBREAK = re.compile(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)")
_HORIZONTAL_SPACE = re.compile(r"[ \f\v]+")
_ALL_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+(?:[.'’/-]\w+)*|[$€£¥₹]|%", flags=re.UNICODE)
_PAGE_OF_TOTAL = re.compile(r"\bpage\s+\d+\s+(?:of|/)\s*\d+\b", flags=re.IGNORECASE)
_PAGE_PREFIX = re.compile(r"\bpage\s+\d+\b", flags=re.IGNORECASE)
_BARE_PAGE = re.compile(r"^\s*(?:p(?:age)?\.?\s*)?\d+(?:\s*/\s*\d+)?\s*$", flags=re.IGNORECASE)
_EDGE_PAGE_NUMBER = re.compile(r"(?:^|[|—–-]\s*)\d+\s*$")


def cleaning_config_fingerprint(config: CleaningConfig) -> str:
    """Return a canonical fingerprint for all cleaning settings."""
    values = config.model_dump(mode="json")
    return fingerprint_mapping(values)


def _remove_controls(text: str) -> str:
    return _ZERO_WIDTH_ARTIFACTS.sub("", _CONTROL_CHARACTERS.sub("", text))


def _normalize_table_whitespace(text: str) -> str:
    """Normalize cell text while preserving tabular row/column separators."""
    rows: list[str] = []
    for raw_row in text.split("\n"):
        cells = raw_row.split("\t")
        normalized_cells = [
            _HORIZONTAL_SPACE.sub(" ", cell.replace("\r", " ")).strip() for cell in cells
        ]
        rows.append("\t".join(normalized_cells))
    return "\n".join(rows).strip()


def normalize_text(text: str, *, kind: ElementType, config: CleaningConfig) -> str:
    """Normalize parser text without changing semantically significant punctuation or numbers."""
    normalized = unicodedata.normalize(config.unicode_form.value, text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    if config.remove_control_characters:
        normalized = _remove_controls(normalized)
    if config.join_hyphenated_linebreaks:
        normalized = _HYPHENATED_LINEBREAK.sub("", normalized)

    if not config.collapse_whitespace:
        return normalized.strip()
    if kind is ElementType.TABLE:
        return _normalize_table_whitespace(normalized)
    return _ALL_SPACE.sub(" ", normalized).strip()


def repeated_pattern_signature(text: str, *, canonicalize_page_numbers: bool) -> str:
    """Canonicalize a header/footer so page-varying numbers can still repeat."""
    signature = _ALL_SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip().casefold()
    if canonicalize_page_numbers:
        signature = _PAGE_OF_TOTAL.sub("page <page> of <total>", signature)
        signature = _PAGE_PREFIX.sub("page <page>", signature)
        if _BARE_PAGE.fullmatch(signature):
            return "<page-number>"
        signature = _EDGE_PAGE_NUMBER.sub(lambda match: match.group(0).rsplit(" ", 1)[0] + " <page>", signature)
    return signature


def is_page_number_pattern(text: str) -> bool:
    """Return whether text is structurally a standalone page-number marker."""
    normalized = _ALL_SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()
    return bool(_BARE_PAGE.fullmatch(normalized) or _PAGE_PREFIX.fullmatch(normalized))


def comparison_tokens(text: str) -> frozenset[str]:
    """Build deterministic case-folded tokens for conservative boilerplate similarity."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return frozenset(match.group(0) for match in _TOKEN.finditer(normalized))


def text_similarity(left: str, right: str) -> float:
    """Return token-set Jaccard similarity in the inclusive range [0, 1]."""
    left_tokens = comparison_tokens(left)
    right_tokens = comparison_tokens(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
