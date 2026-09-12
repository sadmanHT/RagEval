"""Typed project error hierarchy."""


class RagEvalError(Exception):
    """Base class for expected RAG-Eval failures."""


class ValidationError(RagEvalError):
    """Input or configuration validation failed."""


class DataLeakageError(ValidationError):
    """Development/tuning and held-out evaluation data overlap."""


class DocumentParseError(ValidationError):
    """A source document could not be parsed into normalized elements."""


class UnsupportedSourceError(DocumentParseError):
    """A source type or extension is not supported by the ingestion boundary."""


class OCRUnavailableError(DocumentParseError):
    """OCR was required but the configured local OCR path could not run."""


class ProviderError(RagEvalError):
    """An external or local model provider failed."""


class IndexingError(RagEvalError):
    """Index creation or mutation failed."""


class RetrievalError(RagEvalError):
    """Retrieval failed."""


class GenerationError(RagEvalError):
    """Grounded answer generation failed."""


class EvaluationError(RagEvalError):
    """Evaluation execution or aggregation failed."""
