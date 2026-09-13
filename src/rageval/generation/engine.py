"""Application-owned grounded generation, validation, and bounded repair."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence

from pydantic import ValidationError as PydanticValidationError

from rageval.core.errors import GenerationError, ProviderError
from rageval.core.ids import fingerprint_mapping
from rageval.generation.context import ContextAssembler
from rageval.generation.models import (
    GenerationConfig,
    GenerationEngineResult,
    GenerationRepair,
    LLMProviderResponse,
    ProviderGroundedPayload,
)
from rageval.generation.prompts import (
    GROUNDING_SYSTEM_PROMPT,
    build_generation_user_prompt,
    build_repair_user_prompt,
)
from rageval.generation.providers import LLMGenerationProvider
from rageval.models.contracts import GroundedAnswer, RerankResult

_REFUSAL_PHRASES = (
    "insufficient context",
    "not enough context",
    "not enough evidence",
    "cannot answer from the provided context",
    "can't answer from the provided context",
)


def generation_config_fingerprint(config: GenerationConfig) -> str:
    """Fingerprint every application-owned generation/repair behavior."""
    return fingerprint_mapping(config.model_dump(mode="json"))


def _parse_payload(content: str) -> ProviderGroundedPayload:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"provider output is not valid JSON: {exc.msg}") from exc
    try:
        return ProviderGroundedPayload.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValueError(f"provider output does not match grounded schema: {exc}") from exc


def _is_explicit_refusal(answer: str) -> bool:
    normalized = answer.casefold()
    return any(phrase in normalized for phrase in _REFUSAL_PHRASES)


def _payload_errors(
    payload: ProviderGroundedPayload,
    *,
    allowed_chunk_ids: set[str],
    require_citations: bool,
) -> tuple[str, ...]:
    errors: list[str] = []
    cited = [citation.chunk_id for citation in payload.citations]
    nonexistent = sorted(set(cited) - allowed_chunk_ids)
    if nonexistent:
        errors.append(f"citations reference chunk IDs not present in context: {nonexistent}")
    if payload.insufficient_context:
        if payload.citations:
            errors.append("insufficient-context responses must not contain citations")
        if not _is_explicit_refusal(payload.answer):
            errors.append("insufficient-context response must explicitly say context/evidence is insufficient")
    else:
        if require_citations and not payload.citations:
            errors.append("supported answers require at least one citation")
        if _is_explicit_refusal(payload.answer):
            errors.append("answer text refuses while insufficient_context is false")
    return tuple(errors)


class GroundedGenerationEngine:
    """Assemble context, invoke the LLM boundary, and enforce grounding contracts."""

    def __init__(
        self,
        *,
        provider: LLMGenerationProvider,
        assembler: ContextAssembler | None = None,
        config: GenerationConfig | None = None,
    ) -> None:
        self.provider = provider
        self.assembler = assembler or ContextAssembler()
        self.config = config or GenerationConfig()
        self.config_fingerprint = generation_config_fingerprint(self.config)

    async def _provider_call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMProviderResponse:
        try:
            return await self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except asyncio.TimeoutError as exc:
            raise GenerationError("generation provider timed out") from exc
        except ProviderError as exc:
            raise GenerationError(f"generation provider failed: {exc}") from exc

    async def generate(
        self,
        question: str,
        context: Sequence[RerankResult],
    ) -> GenerationEngineResult:
        """Return a validated grounded answer from supplied reranked context only."""
        if not question.strip():
            raise ValueError("question must not be blank")
        assembled = self.assembler.assemble(context)
        if not assembled.chunks:
            answer = GroundedAnswer(
                question=question,
                answer=self.config.insufficient_context_answer,
                citations=[],
                cited_chunk_ids=[],
                insufficient_context=True,
                refusal_reason="no context chunks fit the configured context budget",
                provider=self.provider.name,
                model=self.provider.model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                metadata={
                    "generation_config_fingerprint": self.config_fingerprint,
                    "context_config_fingerprint": assembled.config_fingerprint,
                    "context_chunk_ids": [],
                    "omitted_chunk_ids": list(assembled.omitted_chunk_ids),
                    "duplicate_chunk_ids": list(assembled.duplicate_chunk_ids),
                    "repair_count": 0,
                },
            )
            return GenerationEngineResult(
                answer=answer,
                context=assembled,
                repairs=(),
                config_fingerprint=self.config_fingerprint,
            )

        allowed_ids = set(assembled.included_chunk_ids)
        repairs: list[GenerationRepair] = []
        input_tokens = 0
        output_tokens = 0
        start = time.perf_counter()
        user_prompt = build_generation_user_prompt(question, assembled)
        latest_response: LLMProviderResponse | None = None

        for attempt in range(self.config.max_repair_attempts + 1):
            latest_response = await self._provider_call(
                system_prompt=GROUNDING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            input_tokens += latest_response.input_tokens
            output_tokens += latest_response.output_tokens
            reason: str | None = None
            payload: ProviderGroundedPayload | None = None
            try:
                payload = _parse_payload(latest_response.content)
            except ValueError as exc:
                reason = str(exc)
            if payload is not None:
                validation_errors = _payload_errors(
                    payload,
                    allowed_chunk_ids=allowed_ids,
                    require_citations=self.config.require_citations,
                )
                if not validation_errors:
                    cited_ids = list(dict.fromkeys(citation.chunk_id for citation in payload.citations))
                    latency_ms = (time.perf_counter() - start) * 1000.0
                    answer = GroundedAnswer(
                        question=question,
                        answer=payload.answer,
                        citations=list(payload.citations),
                        cited_chunk_ids=cited_ids,
                        insufficient_context=payload.insufficient_context,
                        refusal_reason=payload.refusal_reason,
                        provider=self.provider.name,
                        model=self.provider.model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        metadata={
                            "generation_config_fingerprint": self.config_fingerprint,
                            "context_config_fingerprint": assembled.config_fingerprint,
                            "context_chunk_ids": list(assembled.included_chunk_ids),
                            "omitted_chunk_ids": list(assembled.omitted_chunk_ids),
                            "duplicate_chunk_ids": list(assembled.duplicate_chunk_ids),
                            "context_tokens": assembled.token_count,
                            "repair_count": len(repairs),
                            "provider_metadata": latest_response.metadata,
                        },
                    )
                    return GenerationEngineResult(
                        answer=answer,
                        context=assembled,
                        repairs=tuple(repairs),
                        config_fingerprint=self.config_fingerprint,
                    )
                reason = "; ".join(validation_errors)

            if attempt >= self.config.max_repair_attempts:
                raise GenerationError(
                    "grounded generation validation failed after "
                    f"{self.config.max_repair_attempts} repair attempt(s): {reason}"
                )
            assert reason is not None
            repairs.append(
                GenerationRepair(
                    attempt=attempt + 1,
                    reason=reason,
                    invalid_output_excerpt=latest_response.content[:500],
                )
            )
            user_prompt = build_repair_user_prompt(
                question=question,
                context=assembled,
                invalid_output=latest_response.content,
                reason=reason,
            )

        raise GenerationError("grounded generation exited repair loop without a validated answer")
