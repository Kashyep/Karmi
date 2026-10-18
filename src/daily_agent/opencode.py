"""Bounded OpenCode Zen chat-completions adapter.

The API's model catalog returns identifiers but not prices or data-use terms. This
dated registry is therefore an explicit allowlist based on the Zen documentation,
not an inference from a model name or a live provider claim.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

ZEN_BASE_URL = "https://opencode.ai/zen/v1"
ZEN_CATALOG_URL = f"{ZEN_BASE_URL}/models"
ZEN_CHAT_URL = f"{ZEN_BASE_URL}/chat/completions"
FREE_RATE_VERSION = "opencode-zen-free-catalog-2026-10-08"
MAX_PROMPT_CHARS = 40_000
MAX_OUTPUT_TOKENS = 4_096
REQUEST_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class FreeModel:
    model_id: str
    private_data_allowed: bool


# Source: https://docs.opencode.ai/docs/zen/ (checked 2026-10-10).
# Private-note use is limited to the three models whose provider terms explicitly
# state zero retention and no model training. All listed IDs have documented
# zero token prices; candidates are rechecked against the live ID catalog.
FREE_MODELS: tuple[FreeModel, ...] = (
    FreeModel("big-pickle", False),
    FreeModel("space-bunny-free", True),
    FreeModel("longcat-2.5-preview-free", True),
    FreeModel("step-5-preview-free", True),
    FreeModel("exo-free", False),
    FreeModel("mimo-v2.6-flash-free", False),
    FreeModel("mimo-v2.5-free", False),
    FreeModel("ling-3.1-flash-free", False),
    FreeModel("ling-3.0-flash-fin-free", False),
    FreeModel("nemotron-3-ultra-free", False),
    FreeModel("nemotron-3.5-lightning-free", False),
)

FREE_MODEL_BY_ID = {model.model_id: model for model in FREE_MODELS}
PRIVATE_DATA_MODEL_IDS = frozenset(
    model.model_id for model in FREE_MODELS if model.private_data_allowed
)


class OpenCodeError(RuntimeError):
    """A provider request failed or returned an invalid response."""


def fetch_catalog(*, api_key: str, transport: httpx.BaseTransport | None = None) -> set[str]:
    """Return the current provider model IDs without exposing the credential."""
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        transport=transport,
        follow_redirects=False,
    ) as client:
        try:
            response = client.get(
                ZEN_CATALOG_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenCodeError("OpenCode model catalog is unavailable") from exc
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise OpenCodeError("OpenCode model catalog has an unexpected format")
    raw_ids = {row.get("id") for row in rows if isinstance(row, dict)}
    ids = {model_id for model_id in raw_ids if isinstance(model_id, str)}
    if len(ids) != len(raw_ids):
        raise OpenCodeError("OpenCode model catalog contains an invalid model id")
    return ids


@dataclass(frozen=True)
class Completion:
    model_id: str
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    finish_reason: str | None
    cost_micro: int


def chat_completion(
    *,
    api_key: str,
    model_id: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
    transport: httpx.BaseTransport | None = None,
) -> Completion:
    """Call one allowlisted zero-price model with no retries and strict payload caps."""
    if model_id not in FREE_MODEL_BY_ID:
        raise OpenCodeError("model is outside the dated free-model allowlist")
    if not api_key or "\n" in api_key or "\r" in api_key:
        raise OpenCodeError("OpenCode API key is missing or invalid")
    if not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise OpenCodeError("output token limit is outside the bounded range")
    if not messages or len(messages) > 32:
        raise OpenCodeError("message count is outside the bounded range")
    if any(
        not isinstance(message.get("role"), str)
        or message["role"] not in {"system", "user", "assistant"}
        or not isinstance(message.get("content"), str)
        for message in messages
    ):
        raise OpenCodeError("only plain-text system, user, and assistant messages are supported")
    if sum(len(message["content"]) for message in messages) > MAX_PROMPT_CHARS:
        raise OpenCodeError("prompt is larger than the provider request limit")

    started_at = time.perf_counter()
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        transport=transport,
        follow_redirects=False,
    ) as client:
        try:
            response = client.post(
                ZEN_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_output_tokens,
                    "temperature": 0.2,
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenCodeError("OpenCode completion failed") from exc
    latency_ms = (time.perf_counter() - started_at) * 1000

    try:
        choice = payload["choices"][0]
        message = choice["message"]
        text = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenCodeError("OpenCode completion returned an unexpected format") from exc
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > max_output_tokens * 12
    ):
        raise OpenCodeError("OpenCode completion returned empty text")
    usage = payload.get("usage") if isinstance(payload, dict) else None
    input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if input_tokens is not None and (not isinstance(input_tokens, int) or input_tokens < 0):
        input_tokens = None
    if output_tokens is not None and (not isinstance(output_tokens, int) or output_tokens < 0):
        output_tokens = None
    return Completion(
        model_id=model_id,
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
        cost_micro=0,
    )
