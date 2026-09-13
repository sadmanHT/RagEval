"""Low-level LLM provider boundary plus deterministic and hosted reference adapters."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

import httpx

from rageval.core.errors import ProviderError
from rageval.generation.models import LLMProviderResponse

_QUESTION_RE = re.compile(r"QUESTION:\n(.*?)\n\nALLOWED_CHUNK_IDS:", re.DOTALL)
_CONTEXT_RE = re.compile(
    r'\[CONTEXT_CHUNK id="([^"]+)"[^\]]*\]\nSOURCE_METADATA:'
    r".*?\nCONTENT:\n(.*?)\n\[/CONTEXT_CHUNK\]",
    re.DOTALL,
)


@runtime_checkable
class LLMGenerationProvider(Protocol):
    """Generate one raw structured response from application-owned prompts."""

    name: str
    model: str

    async def generate(self, *, system_prompt: str, user_prompt: str) -> LLMProviderResponse: ...


class DeterministicFakeGenerationProvider:
    """Credential-free deterministic generation provider for acceptance mechanics."""

    name = "deterministic-fake"
    model = "deterministic-grounded-generator-v1"

    def __init__(
        self,
        *,
        answer: str | None = None,
        refuse_questions: Sequence[str] = (),
        scripted_responses: Sequence[str | Exception] = (),
    ) -> None:
        self.answer = answer
        self._refuse_questions = {" ".join(item.split()) for item in refuse_questions}
        self._scripted_responses = tuple(scripted_responses)
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _question(user_prompt: str) -> str:
        match = _QUESTION_RE.search(user_prompt)
        return " ".join(match.group(1).split()) if match else ""

    async def generate(self, *, system_prompt: str, user_prompt: str) -> LLMProviderResponse:
        self.calls.append((system_prompt, user_prompt))
        call_index = len(self.calls) - 1
        if call_index < len(self._scripted_responses):
            scripted = self._scripted_responses[call_index]
            if isinstance(scripted, Exception):
                raise scripted
            content = scripted
        else:
            question = self._question(user_prompt)
            context_match = _CONTEXT_RE.search(user_prompt)
            if question in self._refuse_questions or context_match is None:
                content = json.dumps(
                    {
                        "answer": (
                            "Insufficient context: the retrieved evidence does not support an "
                            "answer."
                        ),
                        "citations": [],
                        "insufficient_context": True,
                        "refusal_reason": "deterministic fixture marked the question unsupported",
                    },
                    sort_keys=True,
                )
            else:
                chunk_id = context_match.group(1)
                context_text = context_match.group(2).strip()
                answer = self.answer or context_text
                content = json.dumps(
                    {
                        "answer": answer,
                        "citations": [{"chunk_id": chunk_id, "claim": answer}],
                        "insufficient_context": False,
                        "refusal_reason": None,
                    },
                    sort_keys=True,
                )
        return LLMProviderResponse(
            content=content,
            input_tokens=len((system_prompt + " " + user_prompt).split()),
            output_tokens=len(content.split()),
            metadata={"deterministic": True},
        )


class OpenAIGenerationProvider:
    """Hosted OpenAI JSON generation adapter with bounded timeout/retry behavior."""

    name = "openai"
    _RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4.1-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.25,
        max_output_tokens: int = 800,
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
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self.max_output_tokens = max_output_tokens
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

    async def generate(self, *, system_prompt: str, user_prompt: str) -> LLMProviderResponse:
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "max_tokens": self.max_output_tokens,
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
                    message = (
                        f"OpenAI generation request failed after {self.max_attempts} "
                        f"attempts: {exc}"
                    )
                    raise ProviderError(message) from exc
                await self._backoff(attempt)
            except httpx.HTTPError as exc:
                raise ProviderError(f"OpenAI generation request failed: {exc}") from exc
        else:
            raise ProviderError(f"OpenAI generation request failed: {last_error}")

        if response is None:
            raise ProviderError("OpenAI generation request produced no response")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("OpenAI generation response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError("OpenAI generation response is not an object")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError("OpenAI generation response is missing choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderError("OpenAI generation response is missing message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("OpenAI generation response is missing message content")
        usage = payload.get("usage")
        input_tokens = 0
        output_tokens = 0
        if isinstance(usage, dict):
            raw_input = usage.get("prompt_tokens", 0)
            raw_output = usage.get("completion_tokens", 0)
            if isinstance(raw_input, int) and raw_input >= 0:
                input_tokens = raw_input
            if isinstance(raw_output, int) and raw_output >= 0:
                output_tokens = raw_output
        return LLMProviderResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata={"response_id": payload.get("id")},
        )
