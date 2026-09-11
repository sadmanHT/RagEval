import pytest
from pydantic import ValidationError

from rageval.core.settings import Settings


def test_defaults_require_no_cloud_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGEVAL_OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.embedding_provider == "fake"
    assert settings.generation_provider == "fake"


def test_openai_key_required_only_when_openai_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGEVAL_OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="RAGEVAL_OPENAI_API_KEY"):
        Settings(_env_file=None, embedding_provider="openai")


def test_secret_repr_does_not_expose_value() -> None:
    settings = Settings(_env_file=None, openai_api_key="super-secret-value")
    assert "super-secret-value" not in repr(settings)
