from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Outcome(StrEnum):
    ACCEPT = "ACCEPT"
    REPAIR = "REPAIR"
    ESCALATE = "ESCALATE"
    ASK_USER = "ASK_USER"
    SAFE_STOP = "SAFE_STOP"
    DEFERRED = "DEFERRED"


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


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
    policy_version: str
    synthetic: bool = True

