from rageval.core.protocols import (
    EmbeddingProvider,
    ExperimentTracker,
    GenerationProvider,
    RerankerProvider,
    TraceProvider,
)
from rageval.testing.fakes import (
    FakeEmbeddingProvider,
    FakeExperimentTracker,
    FakeGenerationProvider,
    FakeRerankerProvider,
    FakeTraceProvider,
)


def test_fake_providers_satisfy_runtime_protocols() -> None:
    assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)
    assert isinstance(FakeRerankerProvider(), RerankerProvider)
    assert isinstance(FakeGenerationProvider(), GenerationProvider)
    assert isinstance(FakeTraceProvider(), TraceProvider)
    assert isinstance(FakeExperimentTracker(), ExperimentTracker)
