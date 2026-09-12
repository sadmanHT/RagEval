"""Embedding providers used by the Phase 6 dense-retrieval boundary."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx

from rageval.chunking.providers import LocalHashEmbeddingProvider
from rageval.core.errors import ProviderError
from rageval.core.protocols import EmbeddingProvider


@runtime_checkable
class DenseEmbeddingProvider(EmbeddingProvider, Protocol):
    """Embedding provider with schema information required by vector indexes."""

    model: str
    dimension: int


class LocalHashDenseEmbeddingProvider:
    """Deterministic offline dense provider for mechanics and integration tests only."""

    name = "local-hash"
    model = "local-hash-embedding-v1"

    def __init__(self, *, dimension: int = 64) -> None:
        self.dimension = dimension
        self._delegate = LocalHashEmbeddingProvider(dimensions=dimension)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts with the deterministic Phase 5 hashed-vector implementation."""
        return await self._delegate.embed(texts)


class OpenAIEmbeddingProvider:
    """Hosted OpenAI embeddings adapter with explicit model/dimension validation."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-large",
        dimension: int = 3072,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self.model = model
        self.dimension = dimension
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        """Close the internally owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in input order and reject malformed provider responses."""
        if not texts:
            return []
        try:
            response = await self._client.post(
                "/embeddings",
                json={
                    "model": self.model,
                    "input": list(texts),
                    "dimensions": self.dimension,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"OpenAI embedding request failed: {exc}") from exc

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise ProviderError("OpenAI embedding response has an unexpected item count")

        ordered: list[tuple[int, list[float]]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ProviderError("OpenAI embedding response item is not an object")
            index = item.get("index")
            raw_vector = item.get("embedding")
            if not isinstance(index, int) or not isinstance(raw_vector, list):
                raise ProviderError("OpenAI embedding response item is missing index/vector")
            if len(raw_vector) != self.dimension:
                raise ProviderError(
                    "OpenAI embedding dimension mismatch: "
                    f"expected {self.dimension}, got {len(raw_vector)}"
                )
            vector: list[float] = []
            for value in raw_vector:
                if not isinstance(value, (int, float)):
                    raise ProviderError("OpenAI embedding vector contains a non-numeric value")
                vector.append(float(value))
            ordered.append((index, vector))

        ordered.sort(key=lambda pair: pair[0])
        expected_indexes = list(range(len(texts)))
        if [index for index, _ in ordered] != expected_indexes:
            raise ProviderError(
                "OpenAI embedding response indexes are not a complete input ordering"
            )
        return [vector for _, vector in ordered]
