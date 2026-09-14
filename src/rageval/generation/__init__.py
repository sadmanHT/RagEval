"""Grounded generation, bounded context assembly, citations, and retrieval routing."""

from rageval.generation.context import ContextAssembler, context_config_fingerprint
from rageval.generation.engine import GroundedGenerationEngine, generation_config_fingerprint
from rageval.generation.models import (
    AssembledContext,
    ContextAssemblyConfig,
    ContextChunk,
    GenerationConfig,
    GenerationEngineResult,
    GenerationRepair,
    GroundedContextInput,
    GroundedGenerationResponse,
    LLMProviderResponse,
    ProviderGroundedPayload,
    RetrievalRouteDecision,
)
from rageval.generation.providers import (
    DeterministicFakeGenerationProvider,
    LLMGenerationProvider,
    OpenAIGenerationProvider,
)
from rageval.generation.routing import (
    AlwaysRetrieveRouter,
    ConservativeSelfRAGRouter,
    RetrievalRouter,
)
from rageval.generation.service import GroundedGenerationService, RetrievalServiceLike

__all__ = [
    "AlwaysRetrieveRouter",
    "AssembledContext",
    "ConservativeSelfRAGRouter",
    "ContextAssembler",
    "ContextAssemblyConfig",
    "ContextChunk",
    "DeterministicFakeGenerationProvider",
    "GenerationConfig",
    "GenerationEngineResult",
    "GenerationRepair",
    "GroundedContextInput",
    "GroundedGenerationEngine",
    "GroundedGenerationResponse",
    "GroundedGenerationService",
    "LLMGenerationProvider",
    "LLMProviderResponse",
    "OpenAIGenerationProvider",
    "ProviderGroundedPayload",
    "RetrievalRouteDecision",
    "RetrievalRouter",
    "RetrievalServiceLike",
    "context_config_fingerprint",
    "generation_config_fingerprint",
]
