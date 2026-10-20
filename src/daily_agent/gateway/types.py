"""Gateway value types shared by the registry, router, health tracking and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from daily_agent.providers import ProviderCall


class ModelClass(StrEnum):
    """Capability classes, cheapest first. Rank order is the escalation order."""

    ECONOMY = "economy"
    BALANCED = "balanced"
    ADVANCED = "advanced"

    @property
    def rank(self) -> int:
        return _RANKS[self]


_RANKS = {ModelClass.ECONOMY: 0, ModelClass.BALANCED: 1, ModelClass.ADVANCED: 2}


class TaskType(StrEnum):
    """Keys of the registry ``scores`` object (Parakh student-set categories)."""

    CODE = "code"
    MATHS = "maths"
    STUDY = "study"
    HINDI = "hindi"
    MIXED = "mixed"
    SUMMARY = "summary"


@dataclass(frozen=True)
class ChatRequest:
    model_id: str
    messages: tuple[dict[str, str], ...]
    max_output_tokens: int


@dataclass(frozen=True)
class ChatResult:
    text: str
    finish_reason: str | None
    latency_ms: float
    call: ProviderCall


class ProviderError(RuntimeError):
    """A provider call failed. ``kind`` drives circuit-breaker and cooldown handling."""

    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    SERVER = "server"
    AUTH = "auth"
    INVALID = "invalid_response"
    NON_ZERO_PRICE = "non_zero_price"
    REJECTED = "rejected"  # request refused locally (bounds) or 4xx other than 401/403/429

    def __init__(
        self, kind: str, message: str, *, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds
