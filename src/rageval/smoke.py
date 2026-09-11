"""Phase-1 package smoke test entry point."""

from rageval.core.protocols import (
    EmbeddingProvider,
    ExperimentTracker,
    GenerationProvider,
    RerankerProvider,
    TraceProvider,
)
from rageval.core.settings import Settings
from rageval.testing.fakes import (
    FakeEmbeddingProvider,
    FakeExperimentTracker,
    FakeGenerationProvider,
    FakeRerankerProvider,
    FakeTraceProvider,
)


def main() -> None:
    settings = Settings(_env_file=None)
    providers = (
        (FakeEmbeddingProvider(), EmbeddingProvider),
        (FakeRerankerProvider(), RerankerProvider),
        (FakeGenerationProvider(), GenerationProvider),
        (FakeTraceProvider(), TraceProvider),
        (FakeExperimentTracker(), ExperimentTracker),
    )
    if not all(isinstance(provider, protocol) for provider, protocol in providers):
        raise RuntimeError("A deterministic provider no longer satisfies its public protocol")
    print(f"rageval smoke: ok ({settings.app_env})")


if __name__ == "__main__":
    main()
