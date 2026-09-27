"""Telemetry data retention and GDPR/privacy actor purge (ADR-0003).

Enforces retention policies by purging expired records only after they have been exported,
and supports complete right-to-be-forgotten purges for specific pseudonymous actor IDs.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from daily_agent.models import (
    TelemetryFeedback,
    TelemetryModelAttempt,
    TelemetryOpsEvent,
    TelemetryOutcomeSignal,
    TelemetryRouterDecision,
    TelemetryRun,
    TelemetryRunOutcome,
    TelemetryToolEvent,
)

# Keep IN-lists well below SQLite/Postgres bound-parameter limits.
_CHUNK = 500


def _rowcount(res: object) -> int:
    if isinstance(res, CursorResult):
        return int(res.rowcount)
    return 0


def _chunks(ids: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(ids), _CHUNK):
        yield ids[start : start + _CHUNK]


def _delete_runs(session: Session, run_ids: list[str], counts: dict[str, int]) -> None:
    """Delete runs and every per-run child row in bounded chunks, adding to ``counts``."""
    per_run = (
        ("decisions", TelemetryRouterDecision),
        ("attempts", TelemetryModelAttempt),
        ("tool_events", TelemetryToolEvent),
        ("outcomes", TelemetryRunOutcome),
        ("signals", TelemetryOutcomeSignal),
        ("feedback", TelemetryFeedback),
        ("runs", TelemetryRun),
    )
    for chunk in _chunks(run_ids):
        for key, table in per_run:
            counts[key] += _rowcount(
                session.execute(delete(table).where(table.run_id.in_(chunk)))
            )


def purge_expired(
    session: Session,
    *,
    now: datetime,
    retention_days: int,
) -> dict[str, int]:
    """Delete telemetry rows older than the retention cutoff ONLY IF exported.

    Unexported expired runs are preserved and counted. An exported run is also kept while
    any of its signals/feedback is still unexported, so late rows are exported before
    their run disappears. Signals/feedback whose run never reached telemetry (orphans)
    cannot be exported and are deleted once older than the cutoff. Ops events older than
    the cutoff are purged unconditionally.
    Caller commits.
    """
    cutoff = now - timedelta(days=retention_days)

    # 1. Inspect runs completed before cutoff
    expired_runs = list(
        session.execute(
            select(TelemetryRun.run_id, TelemetryRun.export_batch_id).where(
                TelemetryRun.completed_at < cutoff
            )
        ).all()
    )

    exported_run_ids = [row.run_id for row in expired_runs if row.export_batch_id is not None]
    unexported_kept = sum(1 for row in expired_runs if row.export_batch_id is None)
    pending: set[str] = set()
    for chunk in _chunks(exported_run_ids):
        for model in (TelemetryOutcomeSignal, TelemetryFeedback):
            pending.update(
                session.scalars(
                    select(model.run_id).where(
                        model.run_id.in_(chunk), model.export_batch_id.is_(None)
                    )
                )
            )
    purgeable_run_ids = [run_id for run_id in exported_run_ids if run_id not in pending]

    counts: dict[str, int] = {
        "runs": 0,
        "decisions": 0,
        "attempts": 0,
        "tool_events": 0,
        "outcomes": 0,
        "signals": 0,
        "feedback": 0,
        "ops_events": 0,
        "unexported_kept": unexported_kept,
        "pending_children_kept": len(pending),
        "orphans": 0,
    }

    _delete_runs(session, purgeable_run_ids, counts)

    # 2. Delete exported late signals / feedback older than cutoff
    counts["signals"] += _rowcount(
        session.execute(
            delete(TelemetryOutcomeSignal).where(
                TelemetryOutcomeSignal.observed_at < cutoff,
                TelemetryOutcomeSignal.export_batch_id.is_not(None),
            )
        )
    )
    counts["feedback"] += _rowcount(
        session.execute(
            delete(TelemetryFeedback).where(
                TelemetryFeedback.created_at < cutoff,
                TelemetryFeedback.export_batch_id.is_not(None),
            )
        )
    )

    # 3. Orphans: unexported rows older than the cutoff whose run has no telemetry row.
    known_runs = select(TelemetryRun.run_id)
    counts["orphans"] += _rowcount(
        session.execute(
            delete(TelemetryOutcomeSignal).where(
                TelemetryOutcomeSignal.observed_at < cutoff,
                TelemetryOutcomeSignal.export_batch_id.is_(None),
                TelemetryOutcomeSignal.run_id.not_in(known_runs),
            )
        )
    )
    counts["orphans"] += _rowcount(
        session.execute(
            delete(TelemetryFeedback).where(
                TelemetryFeedback.created_at < cutoff,
                TelemetryFeedback.export_batch_id.is_(None),
                TelemetryFeedback.run_id.not_in(known_runs),
            )
        )
    )

    # 4. Delete ops events older than cutoff
    counts["ops_events"] = _rowcount(
        session.execute(
            delete(TelemetryOpsEvent).where(TelemetryOpsEvent.created_at < cutoff)
        )
    )

    session.flush()
    return counts


def purge_actor(session: Session, anonymous_actor_id: str) -> dict[str, int]:
    """Delete every telemetry row associated with a pseudonym, regardless of export status.

    Caller commits.
    """
    actor_run_ids = list(
        session.scalars(
            select(TelemetryRun.run_id).where(
                TelemetryRun.anonymous_actor_id == anonymous_actor_id
            )
        ).all()
    )

    counts: dict[str, int] = {
        "runs": 0,
        "decisions": 0,
        "attempts": 0,
        "tool_events": 0,
        "outcomes": 0,
        "signals": 0,
        "feedback": 0,
    }

    _delete_runs(session, actor_run_ids, counts)

    session.flush()
    return counts
