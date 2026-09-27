import calendar
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.config import Settings
from daily_agent.harness.versioning import BUILTIN_HARNESS
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
    UsagePeriod,
    UsageWindow,
    User,
)
from daily_agent.plans import SYNTHETIC_POLICIES, PlanPolicy
from daily_agent.policy_artifacts.schema import HarnessBundleV1
from daily_agent.providers import (
    TYPESAFE_CALL_ESTIMATE_MICRO,
    TYPESAFE_MODEL_DEFAULT,
    TYPESAFE_PROVIDER,
    ProviderCall,
    classify_intent,
    score_notes_relevance,
)
from daily_agent.routing.registry import LIVE_ROUTE, LOCAL_PROVIDER, LOCAL_ROUTE
from daily_agent.schemas import Outcome

logger = logging.getLogger(__name__)

# Fixed cost of the local deterministic route per completed request.
LOCAL_FAKE_COST_MICRO = 100

# Max notes sent to the live scorer per request — bounds payload size and
# per-request provider latency.
MAX_LIVE_SCORE_NOTES = 10


class BudgetDenied(Exception):
    """Reservation rejected; ``reset_at`` is when the binding limit lifts."""

    def __init__(self, message: str, *, reset_at: datetime) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class IdempotencyConflict(Exception):
    """A request reused an idempotency key with a different payload."""


class ReservationInFlight(Exception):
    """Another live request already holds the reservation for this key."""


# How long a committed reservation may stay RESERVED before another request
# may reclaim it (provider timeout is 15s; this covers retries + jitter).
RESERVATION_LEASE_SECONDS = 120


def current_window_key(now: datetime | None = None) -> tuple[str, datetime]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    reset = datetime(current.year, current.month, current.day, tzinfo=UTC) + timedelta(days=1)
    return current.strftime("%Y-%m-%d"), reset


def current_period_key(now: datetime | None = None) -> tuple[str, datetime]:
    """Calendar-month period key and reset instant — fallback for accounts
    without a subscription anchor."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if current.month == 12:
        reset = datetime(current.year + 1, 1, 1, tzinfo=UTC)
    else:
        reset = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    return current.strftime("%Y-%m"), reset


def subscription_period(anchor: date, now: datetime | None = None) -> tuple[str, datetime]:
    """Current billing period for a subscription anchored to its start date.

    Periods are monthly anniversaries of ``anchor.day``; anchor days beyond a
    month's length clamp to that month's last day (e.g. day 31 -> Feb 28).
    Returns ``(period_key, reset)`` where the key is the period's start date."""
    current = (now or datetime.now(UTC)).astimezone(UTC).date()

    def start_of(year: int, month: int) -> date:
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(anchor.day, last))

    start = start_of(current.year, current.month)
    if start > current:
        prev = (current.year - 1, 12) if current.month == 1 else (current.year, current.month - 1)
        start = start_of(*prev)
    ny, nm = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    reset = datetime(ny, nm, min(anchor.day, calendar.monthrange(ny, nm)[1]), tzinfo=UTC)
    return start.isoformat(), reset


def plan_policy(subscription: Subscription | None) -> PlanPolicy:
    """Effective plan: an active subscription's plan, else the free tier."""
    if subscription is None or subscription.status != "active":
        return SYNTHETIC_POLICIES["ananta"]
    return SYNTHETIC_POLICIES.get(subscription.plan_id, SYNTHETIC_POLICIES["ananta"])


def policy_for(session: Session, account_id: str) -> tuple[Subscription, PlanPolicy]:
    """Like :func:`plan_policy`, but creates a free-tier subscription when missing."""
    subscription = session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if subscription is None:
        subscription = Subscription(account_id=account_id, plan_id="ananta")
        session.add(subscription)
        session.flush()
    return subscription, plan_policy(subscription)


PLAN_TO_TIER: dict[str, int] = {
    "ananta": 1,
    "yanta": 2,
    "trika": 3,
    "part": 4,
}

TIER_TO_PLAN: dict[int, str] = {
    1: "ananta",
    2: "yanta",
    3: "trika",
    4: "part",
}


def tier_for_plan(plan_id: str) -> int:
    return PLAN_TO_TIER.get(plan_id, 1)


def plan_for_tier(tier: int) -> str:
    return TIER_TO_PLAN.get(tier, "ananta")


def sync_theme_progression(session: Session, user: User) -> None:
    """Sets user.unlocked_tier from the account's effective plan, clamping active_theme if needed."""
    subscription = session.scalar(
        select(Subscription).where(Subscription.account_id == user.account_id)
    )
    policy = plan_policy(subscription)
    user.unlocked_tier = tier_for_plan(policy.plan_id)
    if user.active_theme > user.unlocked_tier:
        user.active_theme = user.unlocked_tier
    session.flush()


def sync_account_progression(session: Session, account_id: str) -> None:
    """Syncs theme progression for all users belonging to the given account."""
    subscription = session.scalar(
        select(Subscription).where(Subscription.account_id == account_id)
    )
    policy = plan_policy(subscription)
    unlocked = tier_for_plan(policy.plan_id)
    users = session.scalars(select(User).where(User.account_id == account_id)).all()
    for user in users:
        user.unlocked_tier = unlocked
        if user.active_theme > user.unlocked_tier:
            user.active_theme = user.unlocked_tier
    session.flush()


def ensure_usage_window(session: Session, account_id: str, settings: Settings) -> UsageWindow:
    _subscription, policy = policy_for(session, account_id)
    key, reset = current_window_key()
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
            # Daily spend cannot exceed one request's cap times the daily request
            # count; the real monetary cap is enforced on the UsagePeriod row.
            spend_limit_micro=policy.request_cost_cap_micro * policy.everyday_limit,
            reset_at=reset,
        )
        try:
            with session.begin_nested():
                session.add(window)
                session.flush()
        except IntegrityError:
            window = session.scalar(
                select(UsageWindow).where(
                    UsageWindow.account_id == account_id, UsageWindow.window_key == key
                )
            )
            if window is None:
                raise
    platform = session.get(PlatformBudget, key)
    if platform is None:
        try:
            with session.begin_nested():
                session.add(
                    PlatformBudget(
                        window_key=key,
                        spend_limit_micro=settings.global_daily_budget_micro,
                    )
                )
                session.flush()
        except IntegrityError:
            platform = session.get(PlatformBudget, key)
            if platform is None:
                raise
    return window


def ensure_usage_period(
    session: Session, account_id: str, policy: PlanPolicy, anchor: date | None = None
) -> UsagePeriod:
    now = datetime.now(UTC)
    # The active period is whichever account row resets next in the future —
    # this transparently covers legacy calendar-keyed rows until they expire.
    period = session.scalars(
        select(UsagePeriod)
        .where(UsagePeriod.account_id == account_id, UsagePeriod.reset_at > now)
        .order_by(UsagePeriod.reset_at)
    ).first()
    if period is None:
        if anchor is not None:
            key, reset = subscription_period(anchor, now)
        else:
            key, reset = current_period_key(now)
        period = UsagePeriod(
            account_id=account_id,
            period_key=key,
            spend_limit_micro=policy.period_cost_cap_micro,
            reset_at=reset,
        )
        try:
            with session.begin_nested():
                session.add(period)
                session.flush()
        except IntegrityError:
            period = session.scalars(
                select(UsagePeriod)
                .where(
                    UsagePeriod.account_id == account_id,
                    UsagePeriod.reset_at > now,
                )
                .order_by(UsagePeriod.reset_at)
            ).first()
            if period is None:
                raise
    return period


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
            BudgetReservation.account_id == account_id,
            BudgetReservation.logical_request_id == logical_request_id,
            BudgetReservation.stage == stage,
        )
    )
    now = datetime.now(UTC)
    if existing is not None:
        if existing.status in {ReservationStatus.SETTLED, ReservationStatus.UNKNOWN}:
            return existing
        if existing.status == ReservationStatus.RESERVED:
            if _reservation_is_live(existing, now):
                raise ReservationInFlight(logical_request_id)
            # Lease expired: the worker that owned it is presumed dead. Charge
            # the held estimate as unknown rather than freeing it — remote
            # provider work may already have run.
            settle_budget(
                session,
                existing,
                attempt_id=f"{existing.id}:lease-expired",
                actual_micro=None,
            )
        # RELEASED (or just-reclaimed): re-reserve current capacity on the row.
        window, period = _reserve_hold(session, account_id, settings, amount_micro, now)
        reactivated = session.execute(
            update(BudgetReservation)
            .where(
                BudgetReservation.id == existing.id,
                BudgetReservation.status != ReservationStatus.RESERVED,
            )
            .values(
                status=ReservationStatus.RESERVED,
                reserved_micro=amount_micro,
                usage_window_id=window.id,
                usage_period_id=period.id,
                actual_micro=None,
            )
        )
        if not isinstance(reactivated, CursorResult) or reactivated.rowcount != 1:
            raise ReservationInFlight(logical_request_id)
        session.refresh(existing)
        return existing
    window, period = _reserve_hold(session, account_id, settings, amount_micro, now)
    reservation = BudgetReservation(
        logical_request_id=logical_request_id,
        account_id=account_id,
        usage_window_id=window.id,
        usage_period_id=period.id,
        stage=stage,
        reserved_micro=amount_micro,
    )
    session.add(reservation)
    session.flush()
    return reservation


def _reservation_is_live(reservation: BudgetReservation, now: datetime) -> bool:
    created = reservation.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (now - created).total_seconds() < RESERVATION_LEASE_SECONDS


def _reclaim_stale_reservations(
    session: Session, window_key: str, now: datetime, limit: int = 100
) -> int:
    """Settle-as-unknown abandoned RESERVED rows attached to this window.

    Provider work behind them may already have run, so the held estimate is
    charged rather than refunded. Bounds the damage of a worker that died
    between committing its reservation and settling.
    """
    candidates = session.scalars(
        select(BudgetReservation)
        .join(UsageWindow, BudgetReservation.usage_window_id == UsageWindow.id)
        .where(
            UsageWindow.window_key == window_key,
            BudgetReservation.status == ReservationStatus.RESERVED,
        )
    ).all()
    reclaimed = 0
    for row in candidates[:limit]:
        if _reservation_is_live(row, now):
            continue
        settle_budget(
            session, row, attempt_id=f"{row.id}:lease-expired", actual_micro=None
        )
        reclaimed += 1
    if reclaimed:
        logger.warning(
            "reclaimed %d abandoned reservations in window %s", reclaimed, window_key
        )
    return reclaimed


def _reserve_hold(
    session: Session,
    account_id: str,
    settings: Settings,
    amount_micro: int,
    now: datetime,
) -> tuple[UsageWindow, UsagePeriod]:
    """Apply the guarded counter updates on the current window/period/platform."""
    window = ensure_usage_window(session, account_id, settings)
    _reclaim_stale_reservations(session, window.window_key, now)
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
        logger.warning(
            "budget denied: daily allowance account=%s amount=%s",
            account_id,
            amount_micro,
        )
        raise BudgetDenied("account allowance exhausted", reset_at=window.reset_at)
    subscription, policy = policy_for(session, account_id)
    period = ensure_usage_period(session, account_id, policy, subscription.period_anchor)
    period_result = session.execute(
        update(UsagePeriod)
        .where(
            UsagePeriod.id == period.id,
            UsagePeriod.reserved_micro + UsagePeriod.settled_micro + amount_micro
            <= UsagePeriod.spend_limit_micro,
        )
        .values(reserved_micro=UsagePeriod.reserved_micro + amount_micro)
    )
    if not isinstance(period_result, CursorResult) or period_result.rowcount != 1:
        logger.warning(
            "budget denied: period cap account=%s amount=%s", account_id, amount_micro
        )
        raise BudgetDenied("account period budget exhausted", reset_at=period.reset_at)
    platform_result = session.execute(
        update(PlatformBudget)
        .where(
            PlatformBudget.window_key == window.window_key,
            PlatformBudget.reserved_micro + PlatformBudget.settled_micro + amount_micro
            <= PlatformBudget.spend_limit_micro,
        )
        .values(reserved_micro=PlatformBudget.reserved_micro + amount_micro)
    )
    if not isinstance(platform_result, CursorResult) or platform_result.rowcount != 1:
        logger.warning(
            "budget denied: platform cap account=%s amount=%s", account_id, amount_micro
        )
        raise BudgetDenied(
            "platform spending is temporarily paused", reset_at=window.reset_at
        )
    return window, period


def settle_budget(
    session: Session,
    reservation: BudgetReservation,
    *,
    attempt_id: str,
    actual_micro: int | None,
    calls: list[ProviderCall] | None = None,
) -> None:
    if reservation.status != ReservationStatus.RESERVED:
        return
    known = actual_micro is not None
    settled = reservation.reserved_micro if actual_micro is None else actual_micro
    new_status = ReservationStatus.SETTLED if known else ReservationStatus.UNKNOWN
    # Claim the reservation atomically: concurrent settlers must not double-apply.
    claimed = session.execute(
        update(BudgetReservation)
        .where(
            BudgetReservation.id == reservation.id,
            BudgetReservation.status == ReservationStatus.RESERVED,
        )
        .values(status=new_status, actual_micro=actual_micro)
    )
    if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
        return
    window = session.get(UsageWindow, reservation.usage_window_id)
    if window is None:
        raise RuntimeError("reservation window missing")
    session.execute(
        update(UsageWindow)
        .where(UsageWindow.id == window.id)
        .values(
            reserved_micro=UsageWindow.reserved_micro - reservation.reserved_micro,
            settled_micro=UsageWindow.settled_micro + settled,
        )
    )
    session.execute(
        update(PlatformBudget)
        .where(PlatformBudget.window_key == window.window_key)
        .values(
            reserved_micro=PlatformBudget.reserved_micro - reservation.reserved_micro,
            settled_micro=PlatformBudget.settled_micro + settled,
        )
    )
    if reservation.usage_period_id is not None:
        session.execute(
            update(UsagePeriod)
            .where(UsagePeriod.id == reservation.usage_period_id)
            .values(
                reserved_micro=UsagePeriod.reserved_micro - reservation.reserved_micro,
                settled_micro=UsagePeriod.settled_micro + settled,
            )
        )
    reservation.actual_micro = actual_micro
    reservation.status = new_status
    if calls:
        for call in calls:
            session.add(
                CostLedger(
                    reservation_id=reservation.id,
                    attempt_id=f"{attempt_id}:{call.operation}",
                    provider=call.provider,
                    model_id=call.model_id,
                    cost_micro=call.cost_micro,
                    measurement=call.measurement,
                    rate_version=call.rate_version,
                )
            )
    else:
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
    logger.info(
        "settled reservation %s account=%s status=%s actual_micro=%s",
        reservation.id,
        reservation.account_id,
        new_status,
        actual_micro,
    )


def release_budget(session: Session, reservation: BudgetReservation) -> None:
    """Refund a committed reservation when its request failed before settlement."""
    claimed = session.execute(
        update(BudgetReservation)
        .where(
            BudgetReservation.id == reservation.id,
            BudgetReservation.status == ReservationStatus.RESERVED,
        )
        .values(status=ReservationStatus.RELEASED)
    )
    if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
        return
    window = session.get(UsageWindow, reservation.usage_window_id)
    if window is None:
        raise RuntimeError("reservation window missing")
    session.execute(
        update(UsageWindow)
        .where(UsageWindow.id == window.id)
        .values(
            reserved_micro=UsageWindow.reserved_micro - reservation.reserved_micro,
            everyday_used=UsageWindow.everyday_used - 1,
        )
    )
    session.execute(
        update(PlatformBudget)
        .where(PlatformBudget.window_key == window.window_key)
        .values(
            reserved_micro=PlatformBudget.reserved_micro - reservation.reserved_micro
        )
    )
    if reservation.usage_period_id is not None:
        session.execute(
            update(UsagePeriod)
            .where(UsagePeriod.id == reservation.usage_period_id)
            .values(
                reserved_micro=UsagePeriod.reserved_micro - reservation.reserved_micro
            )
        )
    logger.info(
        "released reservation %s account=%s micro=%s",
        reservation.id,
        reservation.account_id,
        reservation.reserved_micro,
    )


def release_failed_execution(
    session: Session,
    reservation: BudgetReservation,
    *,
    attempt_id: str,
    calls: list[ProviderCall],
) -> None:
    """Refund customer usage but retain paid expense from a failed request.

    If provider usage is unknown, the reserved amount remains in the platform
    spend pool; the provider ledger explicitly retains the unknown measurement.
    """
    release_budget(session, reservation)
    if not calls:
        return
    actual = measured_cost_micro(calls)
    expense = reservation.reserved_micro if actual is None else actual
    window = session.get(UsageWindow, reservation.usage_window_id)
    if window is None:
        raise RuntimeError("reservation window missing")
    session.execute(
        update(PlatformBudget)
        .where(PlatformBudget.window_key == window.window_key)
        .values(settled_micro=PlatformBudget.settled_micro + expense)
    )
    for call in calls:
        session.add(
            CostLedger(
                reservation_id=reservation.id,
                attempt_id=f"{attempt_id}:{call.operation}",
                provider=call.provider,
                model_id=call.model_id,
                cost_micro=call.cost_micro,
                measurement=call.measurement,
                rate_version=call.rate_version,
            )
        )


def scoped_note_query(account_id: str, user_id: str) -> Select[tuple[Note]]:
    return select(Note).where(
        Note.account_id == account_id, Note.owner_user_id == user_id, Note.deleted.is_(False)
    )


def scoped_task_query(account_id: str) -> Select[tuple[Task]]:
    return (
        select(Task)
        .where(Task.account_id == account_id)
        .order_by(Task.completed, Task.title, Task.id)
    )


def create_task_idempotent(
    session: Session, *, account_id: str, user_id: str, title: str, key: str
) -> Task:
    task = session.scalar(
        select(Task).where(Task.account_id == account_id, Task.idempotency_key == key)
    )
    if task is not None:
        if task.title != title:
            raise IdempotencyConflict("idempotency key was reused with a different title")
        return task
    task = Task(account_id=account_id, owner_user_id=user_id, title=title, idempotency_key=key)
    session.add(task)
    session.flush()
    return task


@dataclass(frozen=True)
class AttemptOutcome:
    """One model/provider attempt as observed by the request path (telemetry input)."""

    provider: str
    model: str
    operation: str
    latency_ms: int
    success: bool
    error_type: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_micro: int | None = None
    cost_measurement: str = "unknown"


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _provider_attempt(
    operation: str, calls: list[ProviderCall], *, success: bool, started: float
) -> AttemptOutcome:
    call = calls[0] if calls else None
    error = None if success else ("invalid_output" if call is not None else "provider_error")
    return AttemptOutcome(
        provider=TYPESAFE_PROVIDER,
        model=call.model_id if call is not None else TYPESAFE_MODEL_DEFAULT,
        operation=operation,
        latency_ms=_elapsed_ms(started),
        success=success,
        error_type=error,
        input_tokens=call.input_tokens if call is not None else None,
        output_tokens=call.output_tokens if call is not None else None,
        cost_micro=call.cost_micro if call is not None else None,
        cost_measurement=call.measurement if call is not None else "unknown",
    )


@dataclass(frozen=True)
class ContextManifest:
    text: str
    source_ids: tuple[str, ...]
    estimated_tokens: int
    omitted_source_ids: tuple[str, ...]
    counting_method: str = "utf8-bytes-divided-by-4-estimate"
    provider_calls: tuple[ProviderCall, ...] = ()
    attempts: tuple[AttemptOutcome, ...] = ()


def build_note_context(
    session: Session,
    *,
    account_id: str,
    user_id: str,
    max_tokens: int,
    query_text: str | None = None,
    settings: Settings | None = None,
    live: bool | None = None,
    harness: HarnessBundleV1 = BUILTIN_HARNESS,
) -> ContextManifest:
    """``live=None`` keeps the pre-router rule (live scoring iff live models are enabled)."""
    notes = list(session.scalars(scoped_note_query(account_id, user_id).order_by(Note.updated_at.desc())))
    live_enabled = settings is not None and settings.live_models_enabled
    use_live = live_enabled if live is None else (live and live_enabled)

    provider_calls: list[ProviderCall] = []
    attempts: list[AttemptOutcome] = []
    if query_text and notes and use_live:
        # Score only notes that fit the same bounded context used for classification.
        # Sending full recent notes first could spend outside the selected route's
        # context estimate, even if those notes were omitted from the final context.
        scored_notes: list[Note] = []
        unscored: list[Note] = []
        scoring_tokens = 0
        for index, note in enumerate(notes):
            estimate = max(1, len(note.content.encode("utf-8")) // 4)
            if index < MAX_LIVE_SCORE_NOTES and scoring_tokens + estimate <= max_tokens:
                scored_notes.append(note)
                scoring_tokens += estimate
            else:
                unscored.append(note)
        if scored_notes:
            started = time.perf_counter()
            scores, calls = score_notes_relevance(
                query_text,
                scored_notes,
                prompts=harness.prompts,
                max_retries=harness.recovery.max_provider_retries,
            )
            provider_calls.extend(calls)
            attempts.append(
                _provider_attempt("score", calls, success=scores is not None, started=started)
            )
            if scores is not None:
                notes = [
                    note
                    for _score, note in sorted(
                        zip(scores, scored_notes, strict=True), key=lambda pair: pair[0], reverse=True
                    )
                ] + unscored
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
    return ContextManifest(
        "\n".join(parts),
        tuple(source_ids),
        used,
        tuple(omitted),
        provider_calls=tuple(provider_calls),
        attempts=tuple(attempts),
    )


@dataclass(frozen=True)
class GenerationResult:
    response: str
    outcome: Outcome
    intent: str | None
    route: str
    provider_calls: tuple[ProviderCall, ...] = ()
    attempts: tuple[AttemptOutcome, ...] = ()


def _local_attempt(started: float) -> AttemptOutcome:
    return AttemptOutcome(
        provider=LOCAL_PROVIDER,
        model=LOCAL_ROUTE,
        operation="heuristics",
        latency_ms=_elapsed_ms(started),
        success=True,
        cost_micro=LOCAL_FAKE_COST_MICRO,
        cost_measurement="fixed",
    )


def fake_generate(
    text: str,
    context: ContextManifest,
    *,
    settings: Settings | None = None,
    route: str | None = None,
    harness: HarnessBundleV1 = BUILTIN_HARNESS,
) -> GenerationResult:
    """Execute one request on ``route``.

    ``route=None`` keeps the pre-router rule (live iff live models are enabled). The live
    route still requires live models to be enabled: eligibility already guarantees this and
    the check here is defence in depth.
    """
    lowered = text.casefold().strip()
    if len(text) > 20_000:
        return GenerationResult(
            "This request is too large for the current bounded route. Choose a smaller section.",
            Outcome.DEFERRED,
            intent=None,
            route=LOCAL_ROUTE,
        )

    live_enabled = settings is not None and settings.live_models_enabled
    use_live = live_enabled if route is None else (route == LIVE_ROUTE and live_enabled)
    attempts: list[AttemptOutcome] = []
    if use_live:
        started = time.perf_counter()
        intent, calls = classify_intent(
            text,
            context.text,
            prompts=harness.prompts,
            max_retries=harness.recovery.max_provider_retries,
        )
        attempts.append(_provider_attempt("choice", calls, success=intent is not None, started=started))
        live_attempts = tuple(attempts)
        if intent == "query_memory":
            if context.text:
                return GenerationResult(
                    f"From your saved notes: {context.text}", Outcome.ACCEPT,
                    intent=intent, route=LIVE_ROUTE, provider_calls=tuple(calls),
                    attempts=live_attempts,
                )
            return GenerationResult(
                "I could not find that in your saved notes.", Outcome.ASK_USER,
                intent=intent, route=LIVE_ROUTE, provider_calls=tuple(calls),
                attempts=live_attempts,
            )
        if intent in {"store_memory", "create_task"}:
            # The caller performs the actual Note/Task write for these intents so the
            # response copy is only returned when the mutation really happens.
            label = "note" if intent == "store_memory" else "task"
            return GenerationResult(
                f"I have saved your {label}: {text.strip()}", Outcome.ACCEPT,
                intent=intent, route=LIVE_ROUTE, provider_calls=tuple(calls),
                attempts=live_attempts,
            )
        if intent is not None:
            return GenerationResult(
                f"Draft ready: {text.strip()}", Outcome.ACCEPT,
                intent=intent, route=LIVE_ROUTE, provider_calls=tuple(calls),
                attempts=live_attempts,
            )
        if not harness.recovery.fallback_to_local:
            return GenerationResult(
                "The assistant could not complete this request right now. Please try again.",
                Outcome.DEFERRED,
                intent=None, route=LIVE_ROUTE, provider_calls=tuple(calls),
                attempts=live_attempts,
            )
        # Provider unreachable or malformed response: fall through to heuristics.

    started = time.perf_counter()
    result = _heuristic_generate(text, lowered, context)
    attempts.append(_local_attempt(started))
    return GenerationResult(
        result.response,
        result.outcome,
        intent=None,
        route=LOCAL_ROUTE,
        provider_calls=tuple(calls) if use_live else (),
        attempts=tuple(attempts),
    )


def _heuristic_generate(text: str, lowered: str, context: ContextManifest) -> GenerationResult:
    if lowered.startswith("remember") and not context.text:
        return GenerationResult(
            "I do not have a saved fact for that yet.", Outcome.ASK_USER,
            intent=None, route=LOCAL_ROUTE,
        )
    if "my notes" in lowered or "remember" in lowered:
        if context.text:
            return GenerationResult(
                f"From your saved notes: {context.text}", Outcome.ACCEPT,
                intent=None, route=LOCAL_ROUTE,
            )
        return GenerationResult(
            "I could not find that in your saved notes.", Outcome.ASK_USER,
            intent=None, route=LOCAL_ROUTE,
        )
    return GenerationResult(
        f"Draft ready: {text.strip()}", Outcome.ACCEPT,
        intent=None, route=LOCAL_ROUTE,
    )


def estimate_request_cost_micro(
    policy: PlanPolicy, settings: Settings, *, live: bool | None = None
) -> int:
    """Worst-case reservation for one message: local route plus live provider calls.

    ``live=None`` keeps the pre-router rule (live calls iff live models are enabled).
    """
    estimate = LOCAL_FAKE_COST_MICRO
    use_live = settings.live_models_enabled if live is None else live
    if use_live:
        estimate += 2 * TYPESAFE_CALL_ESTIMATE_MICRO
    return min(policy.request_cost_cap_micro, estimate)


def measured_cost_micro(calls: list[ProviderCall]) -> int | None:
    """Total measured provider cost; ``None`` when any call's cost is unknown."""
    if not calls:
        return LOCAL_FAKE_COST_MICRO
    if any(call.cost_micro is None for call in calls):
        return None
    return sum(call.cost_micro for call in calls if call.cost_micro is not None)


def accounted_provider_calls(
    calls: list[ProviderCall], attempts: list[AttemptOutcome]
) -> list[ProviderCall]:
    """Provider attempts lacking a usage response remain unknown, not free."""
    recorded_operations = {call.operation for call in calls}
    for attempt in attempts:
        if attempt.provider == LOCAL_PROVIDER or attempt.operation in recorded_operations:
            continue
        calls.append(
            ProviderCall(
                provider=attempt.provider,
                model_id=attempt.model,
                operation=attempt.operation,
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                cost_micro=None,
                measurement="unknown",
                rate_version=None,
            )
        )
        recorded_operations.add(attempt.operation)
    return calls


def accept_internal_event(
    session: Session, *, channel: str, source_event_id: str, raw_body: bytes
) -> tuple[InboxEvent, bool]:
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    existing = session.scalar(
        select(InboxEvent).where(
            InboxEvent.channel == channel, InboxEvent.source_event_id == source_event_id
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise IdempotencyConflict(
                "event id was replayed with a different payload"
            )
        return existing, False
    event = InboxEvent(
        channel=channel,
        source_event_id=source_event_id,
        payload_hash=payload_hash,
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
    request_hash: str | None = None,
    run_id: str | None = None,
    route: str | None = None,
) -> Run:
    """Persist the executed route for exact idempotent response replay."""
    run = Run(
        account_id=account_id,
        user_id=user_id,
        logical_request_id=logical_request_id,
        request_hash=request_hash,
        status=RunStatus.COMPLETED if outcome == Outcome.ACCEPT else RunStatus.DEFERRED,
        outcome=outcome,
        response_text=response,
    )
    if run_id is not None:
        run.id = run_id
    session.add(run)
    session.flush()
    session.add(
        OutboxEvent(
            logical_key=f"response:{account_id}:{logical_request_id}",
            run_id=run.id,
            payload=json.dumps({"response": response, "outcome": outcome, "route": route}),
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
