"""Telemetry data retention and GDPR/privacy actor purge (ADR-0003).

Enforces retention policies by purging expired records only after they have been exported,
and supports complete right-to-be-forgotten purges for specific pseudonymous actor IDs.
"""

from __future__ import annotations

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


def _rowcount(res: object) -> int:
    if isinstance(res, CursorResult):
        return int(res.rowcount)
    return 0


def purge_expired(
    session: Session,
    *,
    now: datetime,
    retention_days: int,
) -> dict[str, int]:
    """Delete telemetry rows older than the retention cutoff ONLY IF exported.

    Unexported expired runs are preserved and counted. Ops events older than the cutoff
    are purged unconditionally.
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
    }

    if exported_run_ids:
        counts["decisions"] = _rowcount(
            session.execute(
                delete(TelemetryRouterDecision).where(
                    TelemetryRouterDecision.run_id.in_(exported_run_ids)
                )
            )
        )
        counts["attempts"] = _rowcount(
            session.execute(
                delete(TelemetryModelAttempt).where(
                    TelemetryModelAttempt.run_id.in_(exported_run_ids)
                )
            )
        )
        counts["tool_events"] = _rowcount(
            session.execute(
                delete(TelemetryToolEvent).where(TelemetryToolEvent.run_id.in_(exported_run_ids))
            )
        )
        counts["outcomes"] = _rowcount(
            session.execute(
                delete(TelemetryRunOutcome).where(TelemetryRunOutcome.run_id.in_(exported_run_ids))
            )
        )
        counts["signals"] = _rowcount(
            session.execute(
                delete(TelemetryOutcomeSignal).where(
                    TelemetryOutcomeSignal.run_id.in_(exported_run_ids)
                )
            )
        )
        counts["feedback"] = _rowcount(
            session.execute(
                delete(TelemetryFeedback).where(TelemetryFeedback.run_id.in_(exported_run_ids))
            )
        )
        counts["runs"] = _rowcount(
            session.execute(
                delete(TelemetryRun).where(TelemetryRun.run_id.in_(exported_run_ids))
            )
        )

    # 2. Delete exported late signals / feedback older than cutoff
    del_late_sigs = _rowcount(
        session.execute(
            delete(TelemetryOutcomeSignal).where(
                TelemetryOutcomeSignal.observed_at < cutoff,
                TelemetryOutcomeSignal.export_batch_id.is_not(None),
            )
        )
    )
    counts["signals"] += del_late_sigs

    del_late_fb = _rowcount(
        session.execute(
            delete(TelemetryFeedback).where(
                TelemetryFeedback.created_at < cutoff,
                TelemetryFeedback.export_batch_id.is_not(None),
            )
        )
    )
    counts["feedback"] += del_late_fb

    # 3. Delete ops events older than cutoff
    del_ops = _rowcount(
        session.execute(
            delete(TelemetryOpsEvent).where(TelemetryOpsEvent.created_at < cutoff)
        )
    )
    counts["ops_events"] = del_ops

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

    if actor_run_ids:
        counts["decisions"] = _rowcount(
            session.execute(
                delete(TelemetryRouterDecision).where(
                    TelemetryRouterDecision.run_id.in_(actor_run_ids)
                )
            )
        )
        counts["attempts"] = _rowcount(
            session.execute(
                delete(TelemetryModelAttempt).where(TelemetryModelAttempt.run_id.in_(actor_run_ids))
            )
        )
        counts["tool_events"] = _rowcount(
            session.execute(
                delete(TelemetryToolEvent).where(TelemetryToolEvent.run_id.in_(actor_run_ids))
            )
        )
        counts["outcomes"] = _rowcount(
            session.execute(
                delete(TelemetryRunOutcome).where(TelemetryRunOutcome.run_id.in_(actor_run_ids))
            )
        )
        counts["signals"] = _rowcount(
            session.execute(
                delete(TelemetryOutcomeSignal).where(
                    TelemetryOutcomeSignal.run_id.in_(actor_run_ids)
                )
            )
        )
        counts["feedback"] = _rowcount(
            session.execute(
                delete(TelemetryFeedback).where(TelemetryFeedback.run_id.in_(actor_run_ids))
            )
        )
        counts["runs"] = _rowcount(
            session.execute(
                delete(TelemetryRun).where(TelemetryRun.run_id.in_(actor_run_ids))
            )
        )

    session.flush()
    return counts
