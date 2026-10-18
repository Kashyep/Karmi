from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, StrictInt


class Outcome(StrEnum):
    ACCEPT = "ACCEPT"
    REPAIR = "REPAIR"
    ESCALATE = "ESCALATE"
    ASK_USER = "ASK_USER"
    SAFE_STOP = "SAFE_STOP"
    DEFERRED = "DEFERRED"


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=120)


class NoteView(BaseModel):
    id: str
    content: str
    version: int


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


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str = Field(min_length=8, max_length=120)


class MessageView(BaseModel):
    run_id: str
    status: str
    outcome: Outcome
    response: str
    route: str | None = None
    previous_run_id: str | None = None


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
