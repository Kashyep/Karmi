"""Outcome finalization and signal aggregation across the attribution window (ADR-0003).

Runs whose attribution window has elapsed are finalized by aggregating explicit user
feedback and derived signals (retries, corrections, abandonment) into the run outcome row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.models import (
    TelemetryFeedback,
    TelemetryOutcomeSignal,
    TelemetryRun,
    TelemetryRunOutcome,
)
from daily_agent.telemetry.events import (
    FeedbackType,
    SignalSource,
    SignalStrength,
    SignalType,
)


def finalize_due(
    session: Session,
    *,
    now: datetime,
    window_seconds: int,
    limit: int = 500,
) -> int:
    """Finalize runs whose outcome has finalized_at IS NULL and completed_at <= now - window.

    Returns the number of runs finalized. Caller commits.
    """
    cutoff = now - timedelta(seconds=window_seconds)
    stmt = (
        select(TelemetryRunOutcome, TelemetryRun)
        .join(TelemetryRun, TelemetryRunOutcome.run_id == TelemetryRun.run_id)
        .where(
            TelemetryRunOutcome.finalized_at.is_(None),
            TelemetryRun.completed_at <= cutoff,
        )
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    count = 0
    for outcome, run in rows:
        _finalize_one(session, outcome, run, now=now, window_seconds=window_seconds)
        count += 1
    if count > 0:
        session.flush()
    return count


def finalize_run(session: Session, run_id: str, *, now: datetime) -> bool:
    """Finalize a single run immediately (for testing or manual admin intervention).

    Returns True if found and finalized, False if run or outcome row does not exist.
    """
    outcome = session.get(TelemetryRunOutcome, run_id)
    run = session.get(TelemetryRun, run_id)
    if outcome is None or run is None:
        return False
    _finalize_one(session, outcome, run, now=now, window_seconds=0)
    session.flush()
    return True


def _finalize_one(
    session: Session,
    outcome: TelemetryRunOutcome,
    run: TelemetryRun,
    *,
    now: datetime,
    window_seconds: int,
) -> None:
    # Query all signals for this run
    signals = list(
        session.scalars(
            select(TelemetryOutcomeSignal).where(TelemetryOutcomeSignal.run_id == run.run_id)
        ).all()
    )

    user_retry_signal = any(s.signal_type == SignalType.RETRY.value for s in signals)
    user_accept_signal = any(s.signal_type == SignalType.ACCEPT.value for s in signals)
    user_correction_signal = any(s.signal_type == SignalType.CORRECTION.value for s in signals)

    # Correction distance: latest correction feedback with a distance
    latest_corr_fb = session.scalars(
        select(TelemetryFeedback)
        .where(
            TelemetryFeedback.run_id == run.run_id,
            TelemetryFeedback.feedback_type == FeedbackType.CORRECTION.value,
            TelemetryFeedback.correction_distance.is_not(None),
        )
        .order_by(TelemetryFeedback.created_at.desc())
    ).first()
    correction_distance = latest_corr_fb.correction_distance if latest_corr_fb else None

    # Abandonment: only when outcome is ASK_USER and no later run exists within window
    user_abandon_signal = False
    if outcome.outcome and outcome.outcome.upper() == "ASK_USER":
        window_end = run.completed_at + timedelta(seconds=window_seconds)
        later_run = session.scalar(
            select(TelemetryRun.run_id)
            .where(
                TelemetryRun.anonymous_actor_id == run.anonymous_actor_id,
                TelemetryRun.started_at > run.completed_at,
                TelemetryRun.started_at <= window_end,
            )
            .limit(1)
        )
        if later_run is None:
            user_abandon_signal = True
            # Also insert weak derived no_followup_after_ask signal if not already present
            existing_sig = session.scalar(
                select(TelemetryOutcomeSignal).where(
                    TelemetryOutcomeSignal.run_id == run.run_id,
                    TelemetryOutcomeSignal.signal_type == SignalType.NO_FOLLOWUP_AFTER_ASK.value,
                )
            )
            if existing_sig is None:
                is_late = run.export_batch_id is not None
                session.add(
                    TelemetryOutcomeSignal(
                        signal_id=str(uuid.uuid4()),
                        run_id=run.run_id,
                        signal_type=SignalType.NO_FOLLOWUP_AFTER_ASK.value,
                        strength=SignalStrength.WEAK.value,
                        confidence=0.3,
                        source=SignalSource.DERIVED.value,
                        observed_at=now,
                        late=is_late,
                        export_batch_id=None,
                    )
                )

    outcome.user_retry_signal = user_retry_signal
    outcome.user_accept_signal = user_accept_signal
    outcome.user_correction_signal = user_correction_signal
    outcome.correction_distance = correction_distance
    outcome.user_abandon_signal = user_abandon_signal
    outcome.finalized_at = now
