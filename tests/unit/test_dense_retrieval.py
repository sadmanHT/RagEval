from __future__ import annotations

import json
import uuid
from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from rageval.core.errors import ProviderError
from rageval.models import Domain
from rageval.retrieval.dense import (
    DenseIndexConfig,
    DenseSearchFilter,
    LocalHashDenseEmbeddingProvider,
    OpenAIEmbeddingProvider,
    QdrantDenseIndex,
    point_id_for_chunk,
)
from rageval.testing.fakes import FakeEmbeddingProvider


def test_dense_config_uses_versioned_collection_name() -> None:
    config = DenseIndexConfig(
        collection_base="rageval_test",
        collection_version="fixture_v2",
        vector_size=64,
    )
    assert config.collection_name == "rageval_test__fixture_v2"


def test_dense_search_filter_rejects_reversed_dates() -> None:
    with pytest.raises(ValidationError, match="date_from must be <= date_to"):
        DenseSearchFilter(
            domain=Domain.FINANCIAL,
            date_from=date(2026, 2, 1),
            date_to=date(2026, 1, 1),
        )


def test_point_id_mapping_is_stable_and_qdrant_compatible() -> None:
    first = point_id_for_chunk("chk_fixture_0001")
    second = point_id_for_chunk("chk_fixture_0001")
    changed = point_id_for_chunk("chk_fixture_0002")
    assert first == second
    assert first != changed
    assert str(uuid.UUID(first)) == first


def test_dense_index_rejects_provider_config_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="must match"):
        QdrantDenseIndex(
            provider=FakeEmbeddingProvider(),
            config=DenseIndexConfig(vector_size=3),
        )


@pytest.mark.asyncio
async def test_local_dense_provider_is_deterministic_with_declared_dimension() -> None:
    provider = LocalHashDenseEmbeddingProvider(dimension=16)
    first = await provider.embed(["revenue increased", "legal termination clause"])
    second = await provider.embed(["revenue increased", "legal termination clause"])
    assert first == second
    assert provider.dimension == 16
    assert provider.model == "local-hash-embedding-v1"
    assert all(len(vector) == 16 for vector in first)


@pytest.mark.asyncio
async def test_openai_adapter_preserves_input_order_and_requested_dimension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "text-embedding-3-large"
        assert body["input"] == ["first", "second"]
        assert body["dimensions"] == 3
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.test/v1",
    ) as client:
        provider = OpenAIEmbeddingProvider(
            api_key="test-only",
            dimension=3,
            client=client,
        )
        vectors = await provider.embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


@pytest.mark.asyncio
async def test_openai_adapter_rejects_wrong_vector_dimension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.test/v1",
    ) as client:
        provider = OpenAIEmbeddingProvider(
            api_key="test-only",
            dimension=3,
            client=client,
        )
        with pytest.raises(ProviderError, match="dimension mismatch"):
            await provider.embed(["wrong dimension"])


@pytest.mark.asyncio
async def test_openai_adapter_wraps_http_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.test/v1",
    ) as client:
        provider = OpenAIEmbeddingProvider(api_key="test-only", dimension=3, client=client)
        with pytest.raises(ProviderError, match="request failed"):
            await provider.embed(["provider outage"])
