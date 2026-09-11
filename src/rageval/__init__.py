"""RAG-Eval package."""

from rageval.models.contracts import (
    Chunk,
    Citation,
    DocumentElement,
    DocumentRecord,
    EvaluationExample,
    EvaluationResult,
    GroundedAnswer,
    RerankResult,
    RetrievalResult,
)

__all__ = [
    "Chunk",
    "Citation",
    "DocumentElement",
    "DocumentRecord",
    "EvaluationExample",
    "EvaluationResult",
    "GroundedAnswer",
    "RerankResult",
    "RetrievalResult",
]

__version__ = "0.1.0"
