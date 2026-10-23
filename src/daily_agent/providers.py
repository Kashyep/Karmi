"""External model-provider boundary.

This module is the only place in the codebase permitted to import ``typesafe_sdk``
or reach a live provider. Every call returns a :class:`ProviderCall` record so the
caller can persist real measured cost to the cost ledger — provider spend must
never bypass the budget/ledger machinery.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

TYPESAFE_PROVIDER = "typesafe"
# Resolved model name is read back from each response; this default only labels
# calls that fail before the model is known.
TYPESAFE_MODEL_DEFAULT = "jev-latest"
TYPESAFE_RATE_VERSION = "typesafe-rates-v1"
# Declared rate card in micro-units per 1k tokens. Revisit against the provider's
# published pricing before enabling live models for real users.
TYPESAFE_INPUT_MICRO_PER_1K = 250
TYPESAFE_OUTPUT_MICRO_PER_1K = 1_250
# Worst-case reservation amount per system_one call.
TYPESAFE_CALL_ESTIMATE_MICRO = 10_000
# Hard bounds on call latency: 5s per attempt, at most 2 attempts, 15s total.
TYPESAFE_TIMEOUT_SECONDS = 5.0
TYPESAFE_MAX_RETRIES = 1
TYPESAFE_RETRY_BUDGET_SECONDS = 15.0


@dataclass(frozen=True)
class ProviderCall:
    """A completed provider invocation and its measured cost."""

    provider: str
    model_id: str
    operation: str
    input_tokens: int | None
    output_tokens: int | None
    cost_micro: int | None
    measurement: str
    rate_version: str | None
    # Model/provider the upstream reports having served (may differ from ``model_id``); None
    # when the provider did not say.
    served_model: str | None = None
    served_provider: str | None = None


def _cost_micro(input_tokens: int | None, output_tokens: int | None) -> int | None:
    if input_tokens is None and output_tokens is None:
        return None
    in_cost = (input_tokens or 0) * TYPESAFE_INPUT_MICRO_PER_1K / 1000
    out_cost = (output_tokens or 0) * TYPESAFE_OUTPUT_MICRO_PER_1K / 1000
    return max(1, math.ceil(in_cost + out_cost))


def _record(response: Any, operation: str) -> ProviderCall:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    cost = _cost_micro(input_tokens, output_tokens)
    return ProviderCall(
        provider=TYPESAFE_PROVIDER,
        model_id=getattr(response, "model", None) or TYPESAFE_MODEL_DEFAULT,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_micro=cost,
        measurement="measured" if cost is not None else "unknown",
        rate_version=TYPESAFE_RATE_VERSION if cost is not None else None,
    )


def _client() -> Any:
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    return TypeSafeClient(
        timeout=TYPESAFE_TIMEOUT_SECONDS,
        retry=RetryPolicy(
            max_retries=TYPESAFE_MAX_RETRIES, timeout=TYPESAFE_RETRY_BUDGET_SECONDS
        ),
    )


def classify_intent(text: str) -> tuple[str | None, list[ProviderCall]]:
    """Classify the user's primary intent; ``(None, calls)`` on provider failure."""
    from typesafe_sdk import Choice

    questions = {
        "intent": Choice(
            instructions="What is the primary action the user is asking the assistant to take?",
            criteria={
                "create_task": "The user is instructing the assistant to create a to-do, task, or reminder.",
                "general_draft": "The user is asking for text generation, drafting, or general chat.",
            },
        )
    }
    try:
        with _client() as client:
            response = client.system_one(state={"user_message": text}, questions=questions)
        call = _record(response, "choice")
        intent = response.choices["intent"].choice
        if intent not in {"create_task", "general_draft"}:
            logger.warning("typesafe returned unknown intent %r", intent)
            return None, [call]
        return intent, [call]
    except Exception as exc:
        logger.warning("typesafe classify_intent failed: %s", exc)
        return None, []
