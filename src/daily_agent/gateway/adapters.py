"""Live model adapters behind one ``ChatProvider`` interface.

These adapters (plus ``daily_agent.opencode`` and ``daily_agent.providers`` for TypeSafe) are the
only code allowed to make outbound model HTTP calls. Adapters never retry: retry/fallback policy
belongs to the gateway so it stays bounded and visible.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from daily_agent import opencode
from daily_agent.gateway.registry import RegistryModel
from daily_agent.gateway.types import ChatRequest, ChatResult, ProviderError, StreamChunk
from daily_agent.providers import ProviderCall

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
MAX_PROMPT_CHARS = 120_000
MAX_OUTPUT_TOKENS = 4_096
FREE_MEASUREMENT = "registry-free-model"


class ChatProvider(Protocol):
    name: str

    def complete(self, request: ChatRequest, model: RegistryModel) -> ChatResult: ...
    def stream(self, request: ChatRequest, model: RegistryModel) -> Iterator[StreamChunk]: ...


def _validate_request(request: ChatRequest, *, max_chars: int) -> None:
    if not 1 <= request.max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise ProviderError(
            ProviderError.REJECTED, "output token limit is outside the bounded range"
        )
    if not request.messages or len(request.messages) > 32:
        raise ProviderError(ProviderError.REJECTED, "message count is outside the bounded range")
    for message in request.messages:
        if message.get("role") not in {"system", "user", "assistant"} or not isinstance(
            message.get("content"), str
        ):
            raise ProviderError(
                ProviderError.REJECTED, "only plain-text chat messages are supported"
            )
    if sum(len(m["content"]) for m in request.messages) > max_chars:
        raise ProviderError(
            ProviderError.REJECTED, "prompt is larger than the provider request limit"
        )


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _status_error(response: httpx.Response) -> ProviderError:
    status = response.status_code
    if status == 429:
        return ProviderError(
            ProviderError.RATE_LIMITED,
            "provider rate limit",
            retry_after_seconds=_retry_after(response),
        )
    if status in {401, 402, 403}:
        return ProviderError(ProviderError.AUTH, f"provider refused credentials (HTTP {status})")
    if status == 408 or status >= 500:
        return ProviderError(ProviderError.SERVER, f"provider error (HTTP {status})")
    return ProviderError(ProviderError.REJECTED, f"provider rejected the request (HTTP {status})")


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenRouterProvider:
    """OpenRouter chat-completions (OpenAI-compatible). Free models only."""

    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not api_key or "\n" in api_key or "\r" in api_key:
            raise ProviderError(ProviderError.AUTH, "OpenRouter API key is missing or invalid")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport
        self._clock = clock

    def __repr__(self) -> str:  # never leak the credential through logs or tracebacks
        return "OpenRouterProvider()"

    def complete(self, request: ChatRequest, model: RegistryModel) -> ChatResult:
        _validate_request(request, max_chars=MAX_PROMPT_CHARS)
        body: dict[str, Any] = {
            "model": request.model_id,
            "messages": list(request.messages),
            "max_tokens": request.max_output_tokens,
            "temperature": 0.2,
            "stream": False,
        }
        started = self._clock()
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = client.post(
                    OPENROUTER_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(ProviderError.TIMEOUT, "provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(ProviderError.SERVER, "provider request failed") from exc
        latency_ms = (self._clock() - started) * 1000
        if response.status_code != 200:
            raise _status_error(response)
        try:
            payload: Any = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                ProviderError.INVALID, "provider returned an unexpected format"
            ) from exc
        if not isinstance(text, str):
            raise ProviderError(ProviderError.INVALID, "provider returned non-text content")
        usage = payload.get("usage") if isinstance(payload, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        reported_cost = usage.get("cost")
        if reported_cost is not None:
            try:
                nonzero = Decimal(str(reported_cost)) != 0
            except (InvalidOperation, ValueError):
                nonzero = True
            if nonzero:
                raise ProviderError(
                    ProviderError.NON_ZERO_PRICE,
                    "provider reported a non-zero cost for a free model",
                )
        finish = choice.get("finish_reason") if isinstance(choice, dict) else None
        call = ProviderCall(
            provider=self.name,
            model_id=request.model_id,
            operation="generate",
            input_tokens=_int_or_none(usage.get("prompt_tokens")),
            output_tokens=_int_or_none(usage.get("completion_tokens")),
            cost_micro=0,
            measurement=FREE_MEASUREMENT,
            rate_version=f"registry-{model.snapshot_date}",
        )
        return ChatResult(
            text=text,
            finish_reason=finish if isinstance(finish, str) else None,
            latency_ms=latency_ms,
            call=call,
        )

    def stream(self, request: ChatRequest, model: RegistryModel) -> Iterator[StreamChunk]:
        _validate_request(request, max_chars=MAX_PROMPT_CHARS)
        body: dict[str, Any] = {
            "model": request.model_id,
            "messages": list(request.messages),
            "max_tokens": request.max_output_tokens,
            "temperature": 0.2,
            "stream": True,
        }
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout, read=30.0),
                transport=self._transport,
                follow_redirects=False,
            ) as client, client.stream(
                "POST",
                OPENROUTER_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                if response.status_code != 200:
                    raise _status_error(response)
                finish_reason: str | None = None
                prompt_tokens: int | None = None
                completion_tokens: int | None = None
                for line in response.iter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            payload = json.loads(data_str)
                        except json.JSONDecodeError:
                            logging.getLogger(__name__).debug("skipped malformed provider SSE frame")
                            continue
                        if not isinstance(payload, dict):
                            continue
                        usage = payload.get("usage")
                        if isinstance(usage, dict):
                            reported_cost = usage.get("cost")
                            if reported_cost is not None:
                                try:
                                    nonzero = Decimal(str(reported_cost)) != 0
                                except (InvalidOperation, ValueError):
                                    nonzero = True
                                if nonzero:
                                    raise ProviderError(
                                        ProviderError.NON_ZERO_PRICE,
                                        "provider reported a non-zero cost for a free model",
                                    )
                            if "prompt_tokens" in usage:
                                prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
                            if "completion_tokens" in usage:
                                completion_tokens = _int_or_none(usage.get("completion_tokens"))
                        choices = payload.get("choices")
                        if choices and isinstance(choices, list):
                            choice = choices[0]
                            if isinstance(choice, dict):
                                delta = choice.get("delta")
                                if isinstance(delta, dict) and "content" in delta:
                                    content = delta.get("content")
                                    if content:
                                        yield StreamChunk(text=content)
                                if choice.get("finish_reason"):
                                    finish_reason = choice.get("finish_reason")

                call = ProviderCall(
                    provider=self.name,
                    model_id=request.model_id,
                    operation="generate",
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    cost_micro=0,
                    measurement=FREE_MEASUREMENT,
                    rate_version=f"registry-{model.snapshot_date}",
                )
                yield StreamChunk(finish_reason=finish_reason, call=call)
        except httpx.TimeoutException as exc:
            raise ProviderError(ProviderError.TIMEOUT, "provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(ProviderError.SERVER, "provider request failed") from exc


class OpenCodeProvider:
    """OpenCode Zen free models, via the bounded ``daily_agent.opencode`` client."""

    name = "opencode"

    def __init__(self, *, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

    def __repr__(self) -> str:
        return "OpenCodeProvider()"

    def complete(self, request: ChatRequest, model: RegistryModel) -> ChatResult:
        _validate_request(request, max_chars=opencode.MAX_PROMPT_CHARS)
        try:
            completion = opencode.chat_completion(
                api_key=self._api_key,
                model_id=request.model_id,
                messages=[dict(m) for m in request.messages],
                max_output_tokens=request.max_output_tokens,
                transport=self._transport,
            )
        except opencode.OpenCodeError as exc:
            cause = exc.__cause__
            if isinstance(cause, httpx.HTTPStatusError):
                raise _status_error(cause.response) from exc
            if isinstance(cause, httpx.TimeoutException):
                raise ProviderError(ProviderError.TIMEOUT, "provider request timed out") from exc
            if isinstance(cause, httpx.HTTPError):
                raise ProviderError(ProviderError.SERVER, "provider request failed") from exc
            raise ProviderError(ProviderError.INVALID, str(exc)) from exc
        call = ProviderCall(
            provider=self.name,
            model_id=completion.model_id,
            operation="generate",
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_micro=completion.cost_micro,
            measurement=FREE_MEASUREMENT,
            rate_version=opencode.FREE_RATE_VERSION,
        )
        return ChatResult(
            text=completion.text,
            finish_reason=completion.finish_reason,
            latency_ms=completion.latency_ms,
            call=call,
        )

    def stream(self, request: ChatRequest, model: RegistryModel) -> Iterator[StreamChunk]:
        result = self.complete(request, model)
        yield StreamChunk(text=result.text, finish_reason=result.finish_reason, call=result.call)
