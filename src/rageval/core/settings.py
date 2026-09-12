"""Typed environment-driven application settings."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RAG-Eval settings with provider-specific secret validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAGEVAL_",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_base: str = "rageval_dense"
    qdrant_collection_version: str = "v1"
    redis_url: str = "redis://localhost:6379/0"

    embedding_provider: Literal["fake", "openai", "local"] = "fake"
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    local_embedding_dimensions: int = 64
    openai_base_url: str = "https://api.openai.com/v1"
    reranker_provider: Literal["fake", "cohere", "local"] = "fake"
    generation_provider: Literal["fake", "openai", "anthropic", "local"] = "fake"
    tracing_provider: Literal["disabled", "langfuse"] = "disabled"
    experiment_provider: Literal["disabled", "wandb"] = "disabled"

    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    cohere_api_key: SecretStr | None = None
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    wandb_api_key: SecretStr | None = None
    wandb_project: str = "rag-eval"

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> Settings:
        """Require secrets only for enabled hosted providers."""
        missing: list[str] = []

        if (
            self.embedding_provider == "openai" or self.generation_provider == "openai"
        ) and self.openai_api_key is None:
            missing.append("RAGEVAL_OPENAI_API_KEY")
        if self.generation_provider == "anthropic" and self.anthropic_api_key is None:
            missing.append("RAGEVAL_ANTHROPIC_API_KEY")
        if self.reranker_provider == "cohere" and self.cohere_api_key is None:
            missing.append("RAGEVAL_COHERE_API_KEY")
        if self.tracing_provider == "langfuse":
            if self.langfuse_public_key is None:
                missing.append("RAGEVAL_LANGFUSE_PUBLIC_KEY")
            if self.langfuse_secret_key is None:
                missing.append("RAGEVAL_LANGFUSE_SECRET_KEY")
        if self.experiment_provider == "wandb" and self.wandb_api_key is None:
            missing.append("RAGEVAL_WANDB_API_KEY")

        if missing:
            keys = ", ".join(sorted(set(missing)))
            raise ValueError(f"Missing required provider credentials: {keys}")
        if self.embedding_dimensions < 1 or self.local_embedding_dimensions < 4:
            raise ValueError("embedding dimensions must be positive and local dimensions >= 4")
        return self
