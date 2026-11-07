from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictInt,
    field_validator,
    model_serializer,
    model_validator,
)


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
    # Model id that answered, for client-side display. Not a secret; no key or
    # provider account data is exposed.
    model: str | None = None
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


class UserProfileView(BaseModel):
    id: str
    display_name: str


class UserProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("display_name must not be blank or whitespace-only")
        return stripped


class PlanView(BaseModel):
    id: str
    label: str
    price_inr: int
    everyday_limit: int
    daily_token_limit: int
    input_tokens: int
    output_tokens: int
    request_cost_cap_micro: int
    period_cost_cap_micro: int
    model_classes: list[str]
    min_class: str


class BugReportScreenshotCreate(BaseModel):
    content_type: str
    data_base64: str = Field(max_length=10_000_000)

class BugReportDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_version: str | None = Field(default=None, max_length=128)
    build_number: str | None = Field(default=None, max_length=128)
    git_sha: str | None = Field(default=None, max_length=128)
    os: str | None = Field(default=None, max_length=128)
    os_version: str | None = Field(default=None, max_length=128)
    device_model: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default=None, max_length=128)
    text_scale: float | None = None
    theme: str | None = Field(default=None, max_length=128)
    reduce_transparency: bool | None = None
    plan: str | None = Field(default=None, max_length=128)
    screen: str | None = Field(default=None, max_length=128)
    recent_request_ids: list[str] | None = None
    recent_error_codes: list[str] | None = None
    run_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=128)

    @field_validator("recent_request_ids", "recent_error_codes")
    @classmethod
    def validate_lists(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if len(v) > 10:
                raise ValueError("list may contain at most 10 items")
            for item in v:
                if not isinstance(item, str) or len(item) > 128:
                    raise ValueError("list items must be strings <= 128 chars")
        return v


class BugReportCreate(BaseModel):
    client_report_id: str
    category: Literal["crash", "chat", "ui", "account", "other"]
    description: str
    diagnostics: BugReportDiagnostics
    screenshot: BugReportScreenshotCreate | None = None

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 10 or len(stripped) > 2000:
            raise ValueError("description must be 10..2000 characters after strip")
        return stripped

    @field_validator("client_report_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            parsed = uuid.UUID(v, version=4)
            if str(parsed) != v.lower():
                raise ValueError("invalid uuid")
        except Exception:
            raise ValueError("client_report_id must be a valid UUIDv4") from None
        return v


class BugReportCreatedView(BaseModel):
    id: str
    ticket: str
    status: str
    created_at: str


class BugReportDetailView(BaseModel):
    id: str
    ticket: str
    category: str
    description: str
    diagnostics: dict[str, Any]
    status: str
    has_screenshot: bool
    created_at: str
    updated_at: str


class PatchBugReportBody(BaseModel):
    status: str | None = None
    admin_notes: str | None = Field(default=None, max_length=4000)
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 3 or len(stripped) > 500:
            raise ValueError("reason must be 3..500 characters after strip")
        return stripped

    @model_validator(mode="after")
    def at_least_one(self) -> PatchBugReportBody:
        if self.status is None and self.admin_notes is None:
            raise ValueError("provide at least one of status or admin_notes")
        return self
