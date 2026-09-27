from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from daily_agent.db import Base


def uuid_str() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    QUEUED = "queued"
    WORKING = "working"
    NEEDS_INPUT = "needs_input"
    DEFERRED = "deferred"
    COMPLETED = "completed"
    FAILED = "failed"


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    SETTLED = "settled"
    RELEASED = "released"
    UNKNOWN = "unknown"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    users: Mapped[list["User"]] = relationship(back_populates="account")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("unlocked_tier BETWEEN 1 AND 4", name="check_users_unlocked_tier"),
        CheckConstraint("active_theme BETWEEN 1 AND 4", name="check_users_active_theme"),
        CheckConstraint("active_theme <= unlocked_tier", name="check_users_theme_le_unlocked"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    # Bump to revoke all outstanding tokens for this user.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unlocked_tier: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    active_theme: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    account: Mapped[Account] = relationship(back_populates="users")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)
    plan_id: Mapped[str] = mapped_column(String(20), default="ananta")
    policy_version: Mapped[str] = mapped_column(String(40), default="synthetic-dev-v1")
    status: Mapped[str] = mapped_column(String(20), default="active")
    event_version: Mapped[int] = mapped_column(BigInteger, default=0)
    # Billing periods are monthly anniversaries of this anchor date.
    period_anchor: Mapped[date] = mapped_column(
        Date,
        default=lambda: datetime.now(UTC).date(),
        server_default=func.current_date(),
    )


class UsageWindow(Base):
    __tablename__ = "usage_windows"
    __table_args__ = (UniqueConstraint("account_id", "window_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    window_key: Mapped[str] = mapped_column(String(40))
    everyday_limit: Mapped[int] = mapped_column(Integer)
    everyday_used: Mapped[int] = mapped_column(Integer, default=0)
    spend_limit_micro: Mapped[int] = mapped_column(BigInteger)
    reserved_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    settled_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UsagePeriod(Base):
    """Non-resetting per-billing-period spend accumulator.

    `UsageWindow` resets daily and enforces the *everyday* request-count allowance;
    the monetary `period_cost_cap_micro` lives here so it is not re-granted at
    every midnight boundary.
    """

    __tablename__ = "usage_periods"
    __table_args__ = (UniqueConstraint("account_id", "period_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    period_key: Mapped[str] = mapped_column(String(40))
    spend_limit_micro: Mapped[int] = mapped_column(BigInteger)
    reserved_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    settled_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlatformBudget(Base):
    __tablename__ = "platform_budgets"

    window_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    spend_limit_micro: Mapped[int] = mapped_column(BigInteger)
    reserved_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    settled_micro: Mapped[int] = mapped_column(BigInteger, default=0)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    __table_args__ = (UniqueConstraint("account_id", "logical_request_id", "stage"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    logical_request_id: Mapped[str] = mapped_column(String(160), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    usage_window_id: Mapped[str] = mapped_column(ForeignKey("usage_windows.id"))
    usage_period_id: Mapped[str | None] = mapped_column(
        ForeignKey("usage_periods.id"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(32))
    reserved_micro: Mapped[int] = mapped_column(BigInteger)
    actual_micro: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ReservationStatus.RESERVED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CostLedger(Base):
    __tablename__ = "cost_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("budget_reservations.id"), index=True)
    attempt_id: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(String(120))
    cost_micro: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    measurement: Mapped[str] = mapped_column(String(20))
    rate_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(120))


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    due_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="scheduled")
    idempotency_key: Mapped[str] = mapped_column(String(120))
    # Delivery lease and retry count (see daily_agent.worker).
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("channel", "source_event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    channel: Mapped[str] = mapped_column(String(30))
    source_event_id: Mapped[str] = mapped_column(String(160))
    payload_hash: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("account_id", "logical_request_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    logical_request_id: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=RunStatus.QUEUED)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation: Mapped[int] = mapped_column(Integer, default=1)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("logical_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    logical_key: Mapped[str] = mapped_column(String(255))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider: Mapped[str] = mapped_column(String(40))
    provider_event_id: Mapped[str] = mapped_column(String(160))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    event_version: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(60))
    payload_hash: Mapped[str] = mapped_column(String(64))


# ---- Routing/outcome telemetry (ADR-0003) ----------------------------------------------
# Deliberately no foreign keys to product tables: telemetry is pseudonymous, has its own
# retention (daily_agent.telemetry.retention) and must be writable while product rows churn.
# Nested lists/maps are canonical JSON text so SQLite and PostgreSQL behave identically.


class TelemetryRun(Base):
    __tablename__ = "telemetry_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36))
    session_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anonymous_actor_id: Mapped[str] = mapped_column(String(64), index=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    task_domain: Mapped[str] = mapped_column(String(40))
    tier: Mapped[str] = mapped_column(String(20))
    harness_version: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[str] = mapped_column(String(120))
    feature_schema_version: Mapped[str] = mapped_column(String(80))
    telemetry_schema_version: Mapped[str] = mapped_column(String(40))
    app_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    features_json: Mapped[str] = mapped_column(Text)
    eligible_models_json: Mapped[str] = mapped_column(Text)
    eligibility_rejections_json: Mapped[str] = mapped_column(Text)
    live_fallback_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shadow_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    export_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelemetryRouterDecision(Base):
    __tablename__ = "telemetry_router_decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    policy_version: Mapped[str] = mapped_column(String(120))
    feature_schema_version: Mapped[str] = mapped_column(String(80))
    algorithm: Mapped[str] = mapped_column(String(40))
    selected_model: Mapped[str] = mapped_column(String(120))
    selected_provider: Mapped[str] = mapped_column(String(80))
    selection_probability: Mapped[float] = mapped_column(Float)
    action_probabilities_json: Mapped[str] = mapped_column(Text)
    eligible_models_json: Mapped[str] = mapped_column(Text)
    exploration: Mapped[bool] = mapped_column(Boolean)
    shadow: Mapped[bool] = mapped_column(Boolean)
    agreed_with_live: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TelemetryModelAttempt(Base):
    __tablename__ = "telemetry_model_attempts"

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    operation: Mapped[str] = mapped_column(String(40))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_micro: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cost_measurement: Mapped[str] = mapped_column(String(20))
    success: Mapped[bool] = mapped_column(Boolean)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    retry_number: Mapped[int] = mapped_column(Integer)


class TelemetryToolEvent(Base):
    __tablename__ = "telemetry_tool_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(120))
    attempt_number: Mapped[int] = mapped_column(Integer)
    schema_valid: Mapped[bool] = mapped_column(Boolean)
    execution_success: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(120), nullable=True)


class TelemetryRunOutcome(Base):
    __tablename__ = "telemetry_run_outcomes"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    completed: Mapped[bool] = mapped_column(Boolean)
    first_shot_success: Mapped[bool] = mapped_column(Boolean)
    structured_output_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tool_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer)
    user_retry_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    user_abandon_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    user_accept_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    user_correction_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_latency_ms: Mapped[int] = mapped_column(Integer)
    final_cost_micro: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cost_measurement: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class TelemetryOutcomeSignal(Base):
    __tablename__ = "telemetry_outcome_signals"

    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    signal_type: Mapped[str] = mapped_column(String(40))
    strength: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # True when the signal arrived after its run had already been exported.
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    export_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class TelemetryFeedback(Base):
    __tablename__ = "telemetry_feedback"

    feedback_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    feedback_type: Mapped[str] = mapped_column(String(30))
    original_value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sanitized_corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    export_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class TelemetryOpsEvent(Base):
    __tablename__ = "telemetry_ops_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str | None] = mapped_column(String(120), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TelemetryExportBatch(Base):
    __tablename__ = "telemetry_export_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    run_count: Mapped[int] = mapped_column(Integer)
    signal_count: Mapped[int] = mapped_column(Integer)
    feedback_count: Mapped[int] = mapped_column(Integer)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(500))
