"""Delivery worker: sends queued outbox rows and due reminders to the local test adapter.

Each row is claimed with a conditional UPDATE that re-checks claimability, so
concurrent workers never claim the same row. A worker that crashes mid-delivery
leaves the row leased; once ``lease_until`` passes, another worker reclaims it.
Delivery is therefore at-least-once; every delivery carries a stable key so the
receiving side can drop duplicates. Only a worker that delivered marks a row
delivered, and only while it is still ``delivering``, so a late finisher never
overwrites a failed or already-delivered row. After ``MAX_ATTEMPTS`` the row is
marked failed instead of retried forever.

Only the test adapter exists. Live channel sends stay disabled, and ``main``
refuses to run outside development/test so nothing is marked delivered unsent.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Table, and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.models import OutboxEvent, Reminder

logger = logging.getLogger(__name__)

LEASE_SECONDS = 60
MAX_ATTEMPTS = 5
BATCH_SIZE = 50
POLL_SECONDS = 5

DELIVERING = "delivering"
DELIVERED = "delivered"
FAILED = "failed"

# (delivery_key, payload) -> None; raising leaves the row to be retried after its lease.
Deliver = Callable[[str, str], None]

_OUTBOX: Table = OutboxEvent.__table__  # type: ignore[assignment]
_REMINDERS: Table = Reminder.__table__  # type: ignore[assignment]


def deliver_to_test_adapter(key: str, payload: str) -> None:
    logger.info("test adapter delivered %s (%d bytes)", key, len(payload))


def _claimable(table: Table, status: str, pending: str, now: datetime) -> Any:
    # Rows out of attempts never qualify: _fail_exhausted marks them failed first.
    c = table.c
    return or_(c[status] == pending, and_(c[status] == DELIVERING, c.lease_until < now))


def _claim(
    session: Session, table: Table, status: str, pending: str, now: datetime, *extra: Any
) -> list[str]:
    """Lease up to BATCH_SIZE claimable rows; returns the ids this worker won."""
    c = table.c
    candidates = session.scalars(
        select(c.id).where(_claimable(table, status, pending, now), *extra).limit(BATCH_SIZE)
    ).all()
    claimed: list[str] = []
    for row_id in candidates:
        result = session.execute(
            update(table)
            .where(c.id == row_id, _claimable(table, status, pending, now))
            .values(
                {
                    status: DELIVERING,
                    "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                    "attempts": c.attempts + 1,
                }
            )
        )
        # Commit per row so a contended row stays locked only for its own UPDATE.
        session.commit()
        if isinstance(result, CursorResult) and result.rowcount == 1:
            claimed.append(row_id)
    return claimed


def _finish(session: Session, table: Table, status: str, row_id: str) -> bool:
    c = table.c
    result = session.execute(
        update(table)
        .where(c.id == row_id, c[status] == DELIVERING)
        .values({status: DELIVERED, "lease_until": None})
    )
    session.commit()
    return isinstance(result, CursorResult) and result.rowcount == 1


def _fail_exhausted(session: Session, table: Table, status: str, now: datetime) -> None:
    c = table.c
    result = session.execute(
        update(table)
        .where(c[status] == DELIVERING, c.lease_until < now, c.attempts >= MAX_ATTEMPTS)
        .values({status: FAILED, "lease_until": None})
    )
    if isinstance(result, CursorResult) and result.rowcount:
        logger.warning("marked %d %s rows failed after %d attempts", result.rowcount, table.name, MAX_ATTEMPTS)
    session.commit()


def run_once(
    factory: sessionmaker[Session],
    *,
    now: datetime | None = None,
    deliver: Deliver = deliver_to_test_adapter,
) -> int:
    """Claim and deliver one batch of outbox rows and due reminders; returns rows delivered."""
    now = now or datetime.now(UTC)
    jobs: list[tuple[Table, str, str, str, str]] = []
    with factory() as session:
        _fail_exhausted(session, _OUTBOX, "status", now)
        _fail_exhausted(session, _REMINDERS, "state", now)
        for row_id in _claim(session, _OUTBOX, "status", "queued", now):
            event = session.get(OutboxEvent, row_id)
            if event is not None:
                jobs.append((_OUTBOX, "status", row_id, event.logical_key, event.payload))
        due = _REMINDERS.c.due_at_utc <= now
        for row_id in _claim(session, _REMINDERS, "state", "scheduled", now, due):
            reminder = session.get(Reminder, row_id)
            if reminder is not None:
                payload = json.dumps({"user_id": reminder.owner_user_id, "text": reminder.text})
                jobs.append((_REMINDERS, "state", row_id, f"reminder:{row_id}", payload))
        # Hold no transaction while delivering: delivery is I/O and must not block writers.
        session.commit()

        delivered = 0
        for table, status, row_id, key, payload in jobs:
            try:
                deliver(key, payload)
            except Exception:
                logger.warning("delivery of %s failed; retrying after lease expiry", key, exc_info=True)
                continue
            if _finish(session, table, status, row_id):
                delivered += 1
            else:
                logger.info("%s was already completed by another worker", key)
    return delivered


def main() -> None:
    from daily_agent.config import get_settings
    from daily_agent.db import SessionLocal, create_schema, get_engine

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not get_settings().is_development:
        raise SystemExit("delivery worker only has a test adapter; refusing to run outside development/test")
    create_schema()  # same dev bootstrap the API runs; production uses Alembic
    SessionLocal.configure(bind=get_engine())
    logger.info("delivery worker started (poll=%ss lease=%ss)", POLL_SECONDS, LEASE_SECONDS)
    try:
        while True:
            run_once(SessionLocal)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("delivery worker stopped")


if __name__ == "__main__":
    main()
