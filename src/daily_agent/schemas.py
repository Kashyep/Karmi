from datetime import datetime
from enum import StrEnum

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


class UsageView(BaseModel):
    plan_id: str
    plan_label: str
    everyday_used: int
    everyday_limit: int
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

