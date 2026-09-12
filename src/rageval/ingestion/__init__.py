"""Document loading and normalized parsing."""

from rageval.ingestion.loaders import (
    OCRAdapter,
    TesseractOCRAdapter,
    parse_batch,
    parse_corpus_document,
    parse_document,
)
from rageval.ingestion.models import (
    BatchParseResult,
    OCRMode,
    ParsedDocument,
    ParseFailure,
    ParserConfig,
)

__all__ = [
    "BatchParseResult",
    "OCRAdapter",
    "OCRMode",
    "ParsedDocument",
    "ParseFailure",
    "ParserConfig",
    "TesseractOCRAdapter",
    "parse_batch",
    "parse_corpus_document",
    "parse_document",
]
