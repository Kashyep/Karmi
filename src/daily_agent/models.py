from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    account: Mapped[Account] = relationship(back_populates="users")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)
    plan_id: Mapped[str] = mapped_column(String(20), default="ananta")
    policy_version: Mapped[str] = mapped_column(String(40), default="synthetic-dev-v1")
    status: Mapped[str] = mapped_column(String(20), default="active")
    event_version: Mapped[int] = mapped_column(BigInteger, default=0)


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
    logical_key: Mapped[str] = mapped_column(String(160))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)


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

