from __future__ import annotations

import asyncio
import json

from rageval.serving.app import _stream_query
from rageval.serving.cache import QueryCacheIdentity, build_query_cache_key
from rageval.serving.models import QueryRequest, QueryResponse, StageLatency


def _identity() -> QueryCacheIdentity:
    return QueryCacheIdentity(
        index_fingerprint="1" * 64,
        retrieval_config_fingerprint="2" * 64,
        generation_config_fingerprint="3" * 64,
        model_version="model-v1",
        prompt_version="prompt-v1",
    )


def test_cache_key_invalidates_on_identity_or_filter_changes() -> None:
    base = QueryRequest(question="What is revenue?", domain="financial", top_k=5)
    base_key = build_query_cache_key(base, _identity())

    changed_index = _identity().model_copy(update={"index_fingerprint": "4" * 64})
    changed_prompt = _identity().model_copy(update={"prompt_version": "prompt-v2"})
    changed_filter = QueryRequest(
        question="What is revenue?",
        domain="financial",
        top_k=5,
        filters={"document_id": "doc_12345678"},
    )

    assert build_query_cache_key(base, changed_index) != base_key
    assert build_query_cache_key(base, changed_prompt) != base_key
    assert build_query_cache_key(changed_filter, _identity()) != base_key


class _DisconnectAfterStartRequest:
    def __init__(self, started: asyncio.Event) -> None:
        self.started = started

    async def is_disconnected(self) -> bool:
        await self.started.wait()
        return True


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


async def test_stream_disconnect_cancels_inflight_query() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def execute(payload: QueryRequest, request_id: str) -> QueryResponse:
        del payload, request_id
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()
        return QueryResponse(
            request_id="request-1234",
            answer="unused",
            provider="fixture",
            model="fixture",
            latency=StageLatency(
                retrieval_ms=0.0,
                generation_ms=0.0,
                total_pipeline_ms=0.0,
                api_ms=0.0,
            ),
        )

    chunks = [
        chunk
        async for chunk in _stream_query(
            request=_DisconnectAfterStartRequest(started),  # type: ignore[arg-type]
            payload=QueryRequest(question="disconnect me"),
            request_id="request-1234",
            execute=execute,
            chunk_chars=32,
        )
    ]
    assert chunks == []
    assert started.is_set()
    assert cancelled.is_set()


async def test_stream_failure_is_sanitized(caplog) -> None:
    async def execute(payload: QueryRequest, request_id: str) -> QueryResponse:
        del payload, request_id
        raise RuntimeError("provider token stream-secret-must-not-leak")

    events = [
        json.loads(chunk)
        async for chunk in _stream_query(
            request=_ConnectedRequest(),  # type: ignore[arg-type]
            payload=QueryRequest(question="fail safely"),
            request_id="request-5678",
            execute=execute,
            chunk_chars=32,
        )
    ]

    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"]["code"] == "internal_error"
    assert "stream-secret-must-not-leak" not in str(events)
    assert "stream-secret-must-not-leak" not in caplog.text
    assert "RuntimeError" in caplog.text
