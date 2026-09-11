"""Typed project error hierarchy."""


class RagEvalError(Exception):
    """Base class for expected RAG-Eval failures."""


class ValidationError(RagEvalError):
    """Input or configuration validation failed."""


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
