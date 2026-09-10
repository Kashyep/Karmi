import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.config import Settings
from daily_agent.models import (
    Account,
    BudgetReservation,
    CostLedger,
    InboxEvent,
    Note,
    OutboxEvent,
    PlatformBudget,
    ReservationStatus,
    Run,
    RunStatus,
    Subscription,
    Task,
    UsageWindow,
    User,
)
from daily_agent.plans import SYNTHETIC_POLICIES, PlanPolicy
from daily_agent.schemas import Outcome


class BudgetDenied(Exception):
    pass


def _window(now: datetime | None = None) -> tuple[str, datetime]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    reset = datetime(current.year, current.month, current.day, tzinfo=UTC) + timedelta(days=1)
    return current.strftime("%Y-%m-%d"), reset


def policy_for(session: Session, account_id: str) -> tuple[Subscription, PlanPolicy]:
    subscription = session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if subscription is None or subscription.status != "active":
        plan_id = "ananta"
        if subscription is None:
            subscription = Subscription(account_id=account_id, plan_id=plan_id)
            session.add(subscription)
            session.flush()
    else:
        plan_id = subscription.plan_id
    return subscription, SYNTHETIC_POLICIES.get(plan_id, SYNTHETIC_POLICIES["ananta"])


def ensure_usage_window(session: Session, account_id: str, settings: Settings) -> UsageWindow:
    _subscription, policy = policy_for(session, account_id)
    key, reset = _window()
    window = session.scalar(
        select(UsageWindow).where(
            UsageWindow.account_id == account_id, UsageWindow.window_key == key
        )
    )
    if window is None:
        window = UsageWindow(
            account_id=account_id,
            window_key=key,
            everyday_limit=policy.everyday_limit,
            spend_limit_micro=policy.period_cost_cap_micro,
            reset_at=reset,
        )
        session.add(window)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            window = session.scalar(
                select(UsageWindow).where(
                    UsageWindow.account_id == account_id, UsageWindow.window_key == key
                )
            )
            if window is None:
                raise
    platform = session.get(PlatformBudget, key)
    if platform is None:
        session.add(PlatformBudget(window_key=key, spend_limit_micro=settings.global_daily_budget_micro))
        session.flush()
    return window


def reserve_budget(
    session: Session,
    *,
    settings: Settings,
    account_id: str,
    logical_request_id: str,
    stage: str,
    amount_micro: int,
) -> BudgetReservation:
    if amount_micro <= 0:
        raise ValueError("reservation must be positive")
    existing = session.scalar(
        select(BudgetReservation).where(
            BudgetReservation.logical_request_id == logical_request_id,
            BudgetReservation.stage == stage,
        )
    )
    if existing is not None:
        return existing
    window = ensure_usage_window(session, account_id, settings)
    key = window.window_key
    account_result = session.execute(
        update(UsageWindow)
        .where(
            UsageWindow.id == window.id,
            UsageWindow.reserved_micro + UsageWindow.settled_micro + amount_micro
            <= UsageWindow.spend_limit_micro,
            UsageWindow.everyday_used < UsageWindow.everyday_limit,
        )
        .values(
            reserved_micro=UsageWindow.reserved_micro + amount_micro,
            everyday_used=UsageWindow.everyday_used + 1,
        )
    )
    if not isinstance(account_result, CursorResult) or account_result.rowcount != 1:
        raise BudgetDenied("account allowance exhausted")
    platform_result = session.execute(
        update(PlatformBudget)
        .where(
            PlatformBudget.window_key == key,
            PlatformBudget.reserved_micro + PlatformBudget.settled_micro + amount_micro
            <= PlatformBudget.spend_limit_micro,
        )
        .values(reserved_micro=PlatformBudget.reserved_micro + amount_micro)
    )
    if not isinstance(platform_result, CursorResult) or platform_result.rowcount != 1:
        raise BudgetDenied("platform spending is temporarily paused")
    reservation = BudgetReservation(
        logical_request_id=logical_request_id,
        account_id=account_id,
        usage_window_id=window.id,
        stage=stage,
        reserved_micro=amount_micro,
    )
    session.add(reservation)
    session.flush()
    return reservation


def settle_budget(
    session: Session,
    reservation: BudgetReservation,
    *,
    attempt_id: str,
    actual_micro: int | None,
) -> None:
    if reservation.status != ReservationStatus.RESERVED:
        return
    window = session.get(UsageWindow, reservation.usage_window_id)
    if window is None:
        raise RuntimeError("reservation window missing")
    platform = session.get(PlatformBudget, window.window_key)
    if platform is None:
        raise RuntimeError("platform budget missing")
    known = actual_micro is not None
    settled = reservation.reserved_micro if actual_micro is None else actual_micro
    window.reserved_micro -= reservation.reserved_micro
    window.settled_micro += settled
    platform.reserved_micro -= reservation.reserved_micro
    platform.settled_micro += settled
    reservation.actual_micro = actual_micro
    reservation.status = ReservationStatus.SETTLED if known else ReservationStatus.UNKNOWN
    session.add(
        CostLedger(
            reservation_id=reservation.id,
            attempt_id=attempt_id,
            provider="local-fake",
            model_id="fake-economy",
            cost_micro=actual_micro,
            measurement="measured" if known else "unknown",
            rate_version="synthetic-v1" if known else None,
        )
    )


def scoped_note_query(account_id: str, user_id: str) -> Select[tuple[Note]]:
    return select(Note).where(
        Note.account_id == account_id, Note.owner_user_id == user_id, Note.deleted.is_(False)
    )


def create_task_idempotent(
    session: Session, *, account_id: str, user_id: str, title: str, key: str
) -> Task:
    task = session.scalar(
        select(Task).where(Task.account_id == account_id, Task.idempotency_key == key)
    )
    if task is not None:
        return task
    task = Task(account_id=account_id, owner_user_id=user_id, title=title, idempotency_key=key)
    session.add(task)
    session.flush()
    return task


@dataclass(frozen=True)
class ContextManifest:
    text: str
    source_ids: tuple[str, ...]
    estimated_tokens: int
    omitted_source_ids: tuple[str, ...]
    counting_method: str = "utf8-bytes-divided-by-4-estimate"


def build_note_context(
    session: Session, *, account_id: str, user_id: str, max_tokens: int
) -> ContextManifest:
    notes = list(session.scalars(scoped_note_query(account_id, user_id).order_by(Note.updated_at.desc())))
    parts: list[str] = []
    source_ids: list[str] = []
    omitted: list[str] = []
    used = 0
    for note in notes:
        estimate = max(1, len(note.content.encode("utf-8")) // 4)
        if used + estimate > max_tokens:
            omitted.append(note.id)
            continue
        parts.append(note.content)
        source_ids.append(note.id)
        used += estimate
    return ContextManifest("\n".join(parts), tuple(source_ids), used, tuple(omitted))


def fake_generate(text: str, context: ContextManifest) -> tuple[str, Outcome]:
    lowered = text.casefold().strip()
    if len(text) > 20_000:
        return (
            "This request is too large for the current bounded route. Choose a smaller section.",
            Outcome.DEFERRED,
        )
    if lowered.startswith("remember") and not context.text:
        return "I do not have a saved fact for that yet.", Outcome.ASK_USER
    if "my notes" in lowered or "remember" in lowered:
        if context.text:
            return f"From your saved notes: {context.text}", Outcome.ACCEPT
        return "I could not find that in your saved notes.", Outcome.ASK_USER
    return f"Draft ready: {text.strip()}", Outcome.ACCEPT


def accept_internal_event(
    session: Session, *, channel: str, source_event_id: str, raw_body: bytes
) -> tuple[InboxEvent, bool]:
    existing = session.scalar(
        select(InboxEvent).where(
            InboxEvent.channel == channel, InboxEvent.source_event_id == source_event_id
        )
    )
    if existing is not None:
        return existing, False
    event = InboxEvent(
        channel=channel,
        source_event_id=source_event_id,
        payload_hash=hashlib.sha256(raw_body).hexdigest(),
    )
    session.add(event)
    session.flush()
    return event, True


def persist_completed_run(
    session: Session,
    *,
    account_id: str,
    user_id: str,
    logical_request_id: str,
    response: str,
    outcome: Outcome,
) -> Run:
    run = Run(
        account_id=account_id,
        user_id=user_id,
        logical_request_id=logical_request_id,
        status=RunStatus.COMPLETED if outcome == Outcome.ACCEPT else RunStatus.DEFERRED,
        outcome=outcome,
        response_text=response,
    )
    session.add(run)
    session.flush()
    session.add(
        OutboxEvent(
            logical_key=f"response:{logical_request_id}",
            run_id=run.id,
            payload=json.dumps({"response": response, "outcome": outcome}),
        )
    )
    session.flush()
    return run


def seed_development_identity(session: Session, role: str = "customer") -> User:
    user = session.scalar(select(User).where(User.role == role).limit(1))
    if user is not None:
        return user
    account = session.scalar(select(Account).limit(1))
    if account is None:
        account = Account(name="Synthetic development account")
        session.add(account)
        session.flush()
        session.add(Subscription(account_id=account.id))
    user = User(
        account_id=account.id,
        display_name="Development administrator" if role == "admin" else "Development user",
        role=role,
    )
    session.add(user)
    session.commit()
    return user
