"""Cleaning and normalization boundary for parsed RAG-Eval documents."""

from rageval.cleaning.cleaner import clean_parsed_document
from rageval.cleaning.models import (
    CleanedDocument,
    CleaningConfig,
    CleaningStats,
    RemovalEvidence,
    RemovalReason,
    UnicodeForm,
)
from rageval.cleaning.normalizer import cleaning_config_fingerprint, normalize_text, text_similarity

__all__ = [
    "CleanedDocument",
    "CleaningConfig",
    "CleaningStats",
    "RemovalEvidence",
    "RemovalReason",
    "UnicodeForm",
    "clean_parsed_document",
    "cleaning_config_fingerprint",
    "normalize_text",
    "text_similarity",
]
