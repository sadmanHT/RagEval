import pytest
from pydantic import ValidationError

from rageval.core.settings import Settings


def test_defaults_require_no_cloud_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGEVAL_OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.embedding_provider == "fake"
    assert settings.generation_provider == "fake"
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dimensions == 3072
    assert settings.local_embedding_dimensions == 64
    assert settings.qdrant_collection_base == "rageval_dense"
    assert settings.qdrant_collection_version == "v1"


def test_openai_key_required_only_when_openai_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGEVAL_OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="RAGEVAL_OPENAI_API_KEY"):
        Settings(_env_file=None, embedding_provider="openai")


def test_local_embedding_provider_requires_no_cloud_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGEVAL_OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, embedding_provider="local")
    assert settings.embedding_provider == "local"


def test_invalid_local_embedding_dimension_is_rejected() -> None:
    with pytest.raises(ValidationError, match="local dimensions"):
        Settings(_env_file=None, local_embedding_dimensions=3)


def test_secret_repr_does_not_expose_value() -> None:
    settings = Settings(_env_file=None, openai_api_key="super-secret-value")
    assert "super-secret-value" not in repr(settings)
