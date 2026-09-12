"""Reranker provider interfaces and deterministic/hosted adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable

import httpx

from rageval.core.errors import ProviderError
from rageval.retrieval.rerank.models import RerankProviderResult


@runtime_checkable
class RerankerProvider(Protocol):
    """Score candidate texts for a query and return input indexes."""

    name: str
    model: str

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> tuple[RerankProviderResult, ...]: ...


class DeterministicFakeReranker:
    """Credential-free deterministic reranker for acceptance tests and mechanics only."""

    name = "deterministic-fake"
    model = "deterministic-fake-reranker-v1"

    def __init__(self, score_terms: Mapping[str, float] | None = None) -> None:
        self._score_terms = {
            term.casefold(): float(weight) for term, weight in (score_terms or {}).items()
        }

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> tuple[RerankProviderResult, ...]:
        if top_n < 1:
            raise ValueError("top_n must be positive")
        query_tokens = set(query.casefold().split())
        scored: list[RerankProviderResult] = []
        for index, document in enumerate(documents):
            normalized = document.casefold()
            weighted = sum(
                weight for term, weight in self._score_terms.items() if term in normalized
            )
            overlap = len(query_tokens.intersection(normalized.split()))
            scored.append(RerankProviderResult(index=index, score=weighted + overlap * 0.001))
        scored.sort(key=lambda item: (-item.score, item.index))
        return tuple(scored[: min(top_n, len(scored))])


class CohereReranker:
    """Hosted Cohere Rerank adapter with bounded retry/backoff and strict parsing."""

    name = "cohere"
    _RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "rerank-v3.5",
        base_url: str = "https://api.cohere.com/v2",
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.25,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be non-negative")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
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

    async def _backoff(self, attempt: int) -> None:
        delay = self.backoff_base_seconds * (2**attempt)
        if delay > 0:
            await self._sleep(delay)

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> tuple[RerankProviderResult, ...]:
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_n < 1:
            raise ValueError("top_n must be positive")
        if not documents:
            return ()

        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self._client.post(
                    "/rerank",
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": list(documents),
                        "top_n": min(top_n, len(documents)),
                        "return_documents": False,
                    },
                    timeout=self.timeout_seconds,
                )
                if response.status_code in self._RETRYABLE_STATUSES:
                    if attempt + 1 < self.max_attempts:
                        await self._backoff(attempt)
                        continue
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt + 1 >= self.max_attempts:
                    raise ProviderError(
                        f"Cohere rerank request failed after {self.max_attempts} attempts: {exc}"
                    ) from exc
                await self._backoff(attempt)
            except httpx.HTTPError as exc:
                raise ProviderError(f"Cohere rerank request failed: {exc}") from exc
        else:
            raise ProviderError(f"Cohere rerank request failed: {last_error}")

        if response is None:
            raise ProviderError("Cohere rerank request produced no response")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("Cohere rerank response is not valid JSON") from exc
        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise ProviderError("Cohere rerank response is missing results")

        parsed: list[RerankProviderResult] = []
        seen: set[int] = set()
        for item in raw_results:
            if not isinstance(item, dict):
                raise ProviderError("Cohere rerank result is not an object")
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or not isinstance(score, (int, float)):
                raise ProviderError("Cohere rerank result is missing index/relevance_score")
            if index < 0 or index >= len(documents):
                raise ProviderError("Cohere rerank result index is out of range")
            if index in seen:
                raise ProviderError("Cohere rerank response contains duplicate indexes")
            seen.add(index)
            parsed.append(RerankProviderResult(index=index, score=float(score)))

        parsed.sort(key=lambda item: (-item.score, item.index))
        return tuple(parsed[: min(top_n, len(parsed))])
