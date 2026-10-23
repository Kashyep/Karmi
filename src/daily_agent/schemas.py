from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, StrictInt, model_serializer


class Outcome(StrEnum):
    ACCEPT = "ACCEPT"
    REPAIR = "REPAIR"
    ESCALATE = "ESCALATE"
    ASK_USER = "ASK_USER"
    SAFE_STOP = "SAFE_STOP"
    DEFERRED = "DEFERRED"


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=120)


class TaskView(BaseModel):
    id: str
    title: str
    completed: bool


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    due_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=120)


MAX_HISTORY_TURNS = 20
MAX_HISTORY_TURN_CHARS = 8_000


class HistoryTurn(BaseModel):
    """One earlier chat turn, sent by the client and never stored server-side."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_HISTORY_TURN_CHARS)


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str = Field(min_length=8, max_length=120)
    # Recent turns before ``text``, oldest first. Optional: old clients send none.
    history: list[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


class ServedDebugView(BaseModel):
    """Tester-only: what the provider actually served, mirrors the run's debug columns."""

    served_model: str | None = None
    served_provider: str | None = None
    attempt_count: int | None = None
    fallback_used: bool | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    harness_version: str | None = None


class MessageView(BaseModel):
    run_id: str
    status: str
    outcome: Outcome
    response: str
    route: str | None = None
    previous_run_id: str | None = None
    # Present only for testers: the key is omitted entirely otherwise, never sent as null.
    debug: ServedDebugView | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_debug(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.debug is None:
            data.pop("debug", None)
        return data


FeedbackRating = Literal["up", "down"]
# Fixed vocabulary: never free text, so exported feedback is sanitized by construction.
FeedbackReason = Literal["wrong", "unclear", "too_slow", "other"]


class FeedbackCreate(BaseModel):
    rating: FeedbackRating
    reason: FeedbackReason | None = None


class FeedbackView(BaseModel):
    run_id: str
    rating: FeedbackRating
    reason: FeedbackReason | None = None


class RegenerateCreate(BaseModel):
    # The original prompt is not stored server-side; the client resends it and the server
    # verifies it matches the earlier run before spending anything.
    text: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str = Field(min_length=8, max_length=120)
    reason: FeedbackReason | None = None
    history: list[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


class UsageView(BaseModel):
    plan_id: str
    plan_label: str
    everyday_used: int
    everyday_limit: int
    tokens_used: int = 0
    tokens_limit: int = 0
    reserved_micro: int
    settled_micro: int
    spend_limit_micro: int
    reset_at: datetime
    period_reset_at: datetime
    policy_version: str
    synthetic: bool = True


class ArmoryTier(BaseModel):
    id: int
    key: str
    label: str
    plan_id: str


class ArmoryView(BaseModel):
    unlocked_tier: int
    active_theme: int
    tiers: list[ArmoryTier]


class ActiveThemeUpdate(BaseModel):
    active_theme: StrictInt = Field(ge=1, le=4)


ARMORY_TIERS: tuple[ArmoryTier, ...] = (
    ArmoryTier(id=1, key="ananta", label="Ananta", plan_id="ananta"),
    ArmoryTier(id=2, key="yanta", label="Yanta", plan_id="yanta"),
    ArmoryTier(id=3, key="trika", label="Trika", plan_id="trika"),
    ArmoryTier(id=4, key="parth", label="Parth", plan_id="parth"),
)



class AccessCodeRedeem(BaseModel):
    code: str = Field(min_length=4, max_length=64)


class AccessCodeView(BaseModel):
    plan_id: str
    plan_label: str
    changed: bool
