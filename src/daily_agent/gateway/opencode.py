"""Gateway re-export of daily_agent.opencode definitions."""

from __future__ import annotations

from daily_agent.opencode import (
    FREE_MODEL_BY_ID,
    FREE_MODELS,
    FREE_RATE_VERSION,
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_CHARS,
    PRIVATE_DATA_MODEL_IDS,
    ZEN_BASE_URL,
    ZEN_CATALOG_URL,
    ZEN_CHAT_URL,
    Completion,
    FreeModel,
    OpenCodeError,
    chat_completion,
    fetch_catalog,
)

__all__ = [
    "Completion",
    "FREE_MODEL_BY_ID",
    "FREE_MODELS",
    "FREE_RATE_VERSION",
    "FreeModel",
    "MAX_OUTPUT_TOKENS",
    "MAX_PROMPT_CHARS",
    "OpenCodeError",
    "PRIVATE_DATA_MODEL_IDS",
    "ZEN_BASE_URL",
    "ZEN_CATALOG_URL",
    "ZEN_CHAT_URL",
    "chat_completion",
    "fetch_catalog",
]
