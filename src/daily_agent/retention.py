"""Bounded retention purge for operational tables.

Deletes expired rows in batches of ``settings.retention_batch_size``, one
transaction per batch, so a large backlog never holds a long lock. Only
operational evidence is eligible. Conversation history (chat_messages,
conversations), usage accumulators, billing events and users are never touched.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, Select, delete, exists, select
from sqlalchemy.orm import Session, aliased

from daily_agent.config import Settings
from daily_agent.models import (
    BudgetReservation,
    CostLedger,
    InboxEvent,
    OutboxEvent,
    ReservationStatus,
    RoutingDecision,
    RoutingRecord,
    Run,
    RunStatus,
)

SessionFactory = Callable[[], Session]

# Reservations whose money is final; only these may leave the ledger.
FINAL_RESERVATION_STATUSES = (
    ReservationStatus.SETTLED,
    ReservationStatus.UNKNOWN,
    ReservationStatus.RELEASED,
)
# Runs still in flight must never be purged regardless of age.
ACTIVE_RUN_STATUSES = (RunStatus.QUEUED, RunStatus.WORKING, "streaming")


def _cutoff(now: datetime, days: int) -> datetime:
    return now.astimezone(UTC) - timedelta(days=days)


def _delete_in_batches(
    session_factory: SessionFactory,
    model: type[Any],
    pk: Any,
    criteria: Select[Any],
    batch_size: int,
) -> int:
    """Delete rows selected by ``criteria`` (whose first column is ``pk``), batch by batch.

    The batch is materialised as a derived table so the inner select never
    auto-correlates to the DELETE target, which is portable across SQLite and
    PostgreSQL.
    """
    total = 0
    while True:
        with session_factory() as session:
            batch = criteria.limit(batch_size).subquery()
            result = session.execute(delete(model).where(pk.in_(select(batch.c[0]))))
            if not isinstance(result, CursorResult):
                raise TypeError("retention delete did not return a CursorResult")
            deleted = int(result.rowcount)
            session.commit()
        total += deleted
        if deleted < batch_size:
            return total


def _purge_inbox(session_factory: SessionFactory, settings: Settings, now: datetime) -> int:
    cutoff = _cutoff(now, settings.retention_inbox_days)
    criteria = select(InboxEvent.id).where(InboxEvent.accepted_at < cutoff)
    return _delete_in_batches(
        session_factory, InboxEvent, InboxEvent.id, criteria, settings.retention_batch_size
    )


def _purge_routing_records(
    session_factory: SessionFactory, settings: Settings, now: datetime
) -> int:
    cutoff = _cutoff(now, settings.retention_routing_days)
    criteria = select(RoutingRecord.run_id).where(RoutingRecord.completed_at < cutoff)
    return _delete_in_batches(
        session_factory,
        RoutingRecord,
        RoutingRecord.run_id,
        criteria,
        settings.retention_batch_size,
    )


def _purge_routing_decisions(
    session_factory: SessionFactory, settings: Settings, now: datetime
) -> int:
    cutoff = _cutoff(now, settings.retention_routing_days)
    criteria = select(RoutingDecision.id).where(RoutingDecision.created_at < cutoff)
    return _delete_in_batches(
        session_factory,
        RoutingDecision,
        RoutingDecision.id,
        criteria,
        settings.retention_batch_size,
    )


def _purge_cost_ledger(session_factory: SessionFactory, settings: Settings, now: datetime) -> int:
    cutoff = _cutoff(now, settings.retention_ledger_days)
    final_reservations = select(BudgetReservation.id).where(
        BudgetReservation.status.in_(FINAL_RESERVATION_STATUSES)
    )
    criteria = select(CostLedger.id).where(
        CostLedger.created_at < cutoff,
        CostLedger.reservation_id.in_(final_reservations),
    )
    return _delete_in_batches(
        session_factory, CostLedger, CostLedger.id, criteria, settings.retention_batch_size
    )


def _purge_budget_reservations(
    session_factory: SessionFactory, settings: Settings, now: datetime
) -> int:
    """Drop final reservations past the ledger horizon once their ledger rows are gone."""
    cutoff = _cutoff(now, settings.retention_ledger_days)
    row = aliased(BudgetReservation)
    ledger = aliased(CostLedger)
    criteria = select(row.id).where(
        row.created_at < cutoff,
        row.status.in_(FINAL_RESERVATION_STATUSES),
        ~exists().where(ledger.reservation_id == row.id),
    )
    return _delete_in_batches(
        session_factory,
        BudgetReservation,
        BudgetReservation.id,
        criteria,
        settings.retention_batch_size,
    )


def _purge_outbox(session_factory: SessionFactory, settings: Settings, now: datetime) -> int:
    """Outbox rows carry no timestamp; age comes from the owning run."""
    cutoff = _cutoff(now, settings.retention_outbox_days)
    old_runs = select(Run.id).where(Run.created_at < cutoff)
    criteria = select(OutboxEvent.id).where(
        OutboxEvent.status != "queued",
        OutboxEvent.run_id.in_(old_runs),
    )
    return _delete_in_batches(
        session_factory, OutboxEvent, OutboxEvent.id, criteria, settings.retention_batch_size
    )


def _purge_runs(session_factory: SessionFactory, settings: Settings, now: datetime) -> int:
    cutoff = _cutoff(now, settings.retention_runs_days)
    criteria = select(Run.id).where(
        Run.created_at < cutoff,
        Run.status.not_in(ACTIVE_RUN_STATUSES),
    )
    return _delete_in_batches(session_factory, Run, Run.id, criteria, settings.retention_batch_size)


def purge_expired(
    session_factory: SessionFactory,
    settings: Settings,
    now: datetime | None = None,
    only: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """Delete expired operational rows; returns rows deleted per table.

    Ordering matters: ledger rows go before the reservations they reference, and
    outbox rows go before the runs they reference, so one pass clears each chain.
    ``only`` restricts the pass to the named tables (keys of the returned dict).
    """
    current = now if now is not None else datetime.now(UTC)
    passes: dict[str, Callable[[SessionFactory, Settings, datetime], int]] = {
        "inbox_events": _purge_inbox,
        "routing_records": _purge_routing_records,
        "routing_decisions": _purge_routing_decisions,
        "cost_ledger": _purge_cost_ledger,
        "budget_reservations": _purge_budget_reservations,
        "outbox_events": _purge_outbox,
        "runs": _purge_runs,
    }
    selected = passes if only is None else {name: passes[name] for name in only}
    return {name: fn(session_factory, settings, current) for name, fn in selected.items()}
