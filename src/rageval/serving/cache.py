"""Correctness-scoped query caching for Phase 13 serving."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from pydantic import Field
from redis.asyncio import Redis

from rageval.models.contracts import ContractModel
from rageval.serving.models import QueryRequest


class QueryCacheIdentity(ContractModel):
    """All external identities that can make a cached grounded answer stale."""

    index_fingerprint: str = Field(min_length=16)
    retrieval_config_fingerprint: str = Field(min_length=16)
    generation_config_fingerprint: str = Field(min_length=16)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class QueryCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...

    async def ping(self) -> None: ...

    async def aclose(self) -> None: ...


def build_query_cache_key(request: QueryRequest, identity: QueryCacheIdentity) -> str:
    """Fingerprint request semantics plus index/config/model/prompt identity."""

    payload = {
        "question": " ".join(request.question.split()),
        "domain": request.domain.value if request.domain is not None else None,
        "filters": request.filters.model_dump(mode="json"),
        "top_k": request.top_k,
        "identity": identity.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"rageval:query:v1:{digest}"


class RedisQueryCache:
    """Async Redis cache. The caller controls TTL and cache-key identity."""

    def __init__(self, client: Redis) -> None:
        self.client = client

    @classmethod
    def from_url(cls, url: str) -> RedisQueryCache:
        client = Redis.from_url(url, decode_responses=True)
        return cls(client)

    async def get(self, key: str) -> str | None:
        value = await self.client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        await self.client.set(key, value, ex=ttl_seconds)

    async def ping(self) -> None:
        await self.client.ping()

    async def aclose(self) -> None:
        await self.client.aclose()


class MemoryQueryCache:
    """Deterministic in-memory cache used by unit tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        del ttl_seconds
        self.values[key] = value

    async def ping(self) -> None:
        return None

    async def aclose(self) -> None:
        return None
