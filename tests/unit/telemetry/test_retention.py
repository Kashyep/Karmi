"""Unit tests for telemetry retention policies and actor purging (ADR-0003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.models import (
    TelemetryFeedback,
    TelemetryOutcomeSignal,
    TelemetryRun,
    TelemetryRunOutcome,
)
from daily_agent.telemetry import retention, writer
from tests.unit.telemetry.conftest import (
    build_synthetic_feedback_record,
    build_synthetic_ops_event,
    build_synthetic_run_record,
    build_synthetic_signal_record,
    make_hex64,
    make_uuid,
)


def test_purge_expired_deletes_only_exported_and_preserves_unexported(
    temp_db: sessionmaker[Session],
) -> None:
    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    retention_days = 90
    old_time = now - timedelta(days=100)
    recent_time = now - timedelta(days=10)

    # Run 1: old, exported
    run_old_exported = build_synthetic_run_record(
        run_id=make_uuid(1001),
        started_at=old_time,
        completed_at=old_time,
    )
    # Run 2: old, UNEXPORTED
    run_old_unexported = build_synthetic_run_record(
        run_id=make_uuid(1002),
        started_at=old_time,
        completed_at=old_time,
    )
    # Run 3: recent, exported
    run_recent_exported = build_synthetic_run_record(
        run_id=make_uuid(1003),
        started_at=recent_time,
        completed_at=recent_time,
    )

    ops_old = build_synthetic_ops_event(event_id=make_uuid(1004), created_at=old_time)
    ops_recent = build_synthetic_ops_event(event_id=make_uuid(1005), created_at=recent_time)

    with temp_db() as session:
        writer.persist_events(
            session,
            [run_old_exported, run_old_unexported, run_recent_exported, ops_old, ops_recent],
            now=now,
            attribution_window_seconds=3600,
        )
        session.commit()

    # Mark run 1 and run 3 as exported
    with temp_db() as session:
        r1 = session.get(TelemetryRun, make_uuid(1001))
        assert r1 is not None
        r1.export_batch_id = make_hex64("1")

        r3 = session.get(TelemetryRun, make_uuid(1003))
        assert r3 is not None
        r3.export_batch_id = make_hex64("3")
        session.commit()

    # Purge
    with temp_db() as session:
        counts = retention.purge_expired(session, now=now, retention_days=retention_days)
        session.commit()

    assert counts["runs"] == 1
    assert counts["unexported_kept"] == 1
    assert counts["ops_events"] == 1

    # Verify run 1 is deleted, run 2 is kept, run 3 is kept
    with temp_db() as session:
        assert session.get(TelemetryRun, make_uuid(1001)) is None
        assert session.get(TelemetryRunOutcome, make_uuid(1001)) is None

        assert session.get(TelemetryRun, make_uuid(1002)) is not None
        assert session.get(TelemetryRunOutcome, make_uuid(1002)) is not None

        assert session.get(TelemetryRun, make_uuid(1003)) is not None


def test_purge_keeps_expired_run_until_its_late_feedback_is_exported_and_drops_orphans(
    temp_db: sessionmaker[Session],
) -> None:
    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    old_time = now - timedelta(days=100)
    run = build_synthetic_run_record(
        run_id=make_uuid(3001), started_at=old_time, completed_at=old_time
    )
    with temp_db() as session:
        writer.persist_events(session, [run], now=old_time, attribution_window_seconds=3600)
        exported = session.get(TelemetryRun, make_uuid(3001))
        assert exported is not None
        exported.export_batch_id = make_hex64("1")
        session.commit()
    late = build_synthetic_feedback_record(
        feedback_id=make_uuid(3002), run_id=make_uuid(3001), created_at=old_time
    )
    orphan = build_synthetic_feedback_record(
        feedback_id=make_uuid(3003), run_id=make_uuid(3999), created_at=old_time
    )
    with temp_db() as session:
        writer.persist_events(
            session, [late, orphan], now=old_time, attribution_window_seconds=3600
        )
        session.commit()

    with temp_db() as session:
        counts = retention.purge_expired(session, now=now, retention_days=90)
        session.commit()
    assert counts["runs"] == 0 and counts["pending_children_kept"] == 1
    # Orphan feedback plus its strong signal can never be exported; both are purged.
    assert counts["orphans"] == 2
    with temp_db() as session:
        assert session.get(TelemetryRun, make_uuid(3001)) is not None
        pending = session.get(TelemetryFeedback, make_uuid(3002))
        assert pending is not None and pending.export_batch_id is None
        assert session.get(TelemetryFeedback, make_uuid(3003)) is None
        pending.export_batch_id = make_hex64("2")
        for signal in session.scalars(
            select(TelemetryOutcomeSignal).where(TelemetryOutcomeSignal.run_id == make_uuid(3001))
        ):
            signal.export_batch_id = make_hex64("2")
        session.commit()

    with temp_db() as session:
        counts = retention.purge_expired(session, now=now, retention_days=90)
        session.commit()
    assert counts["runs"] == 1 and counts["feedback"] == 1
    with temp_db() as session:
        assert session.get(TelemetryRun, make_uuid(3001)) is None
        assert session.get(TelemetryFeedback, make_uuid(3002)) is None


def test_purge_actor_removes_single_actor_completely(temp_db: sessionmaker[Session]) -> None:
    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    actor_target = make_hex64("a")
    actor_other = make_hex64("b")

    run_target1 = build_synthetic_run_record(
        run_id=make_uuid(2001),
        anonymous_actor_id=actor_target,
    )
    run_target2 = build_synthetic_run_record(
        run_id=make_uuid(2002),
        anonymous_actor_id=actor_target,
    )
    run_other = build_synthetic_run_record(
        run_id=make_uuid(2003),
        anonymous_actor_id=actor_other,
    )

    sig_target = build_synthetic_signal_record(run_id=make_uuid(2001))
    fb_target = build_synthetic_feedback_record(run_id=make_uuid(2002))

    with temp_db() as session:
        writer.persist_events(
            session,
            [run_target1, run_target2, run_other, sig_target, fb_target],
            now=now,
            attribution_window_seconds=3600,
        )
        session.commit()

    # Purge target actor
    with temp_db() as session:
        counts = retention.purge_actor(session, actor_target)
        session.commit()

    assert counts["runs"] == 2

    # Verify target actor data deleted, other actor untouched
    with temp_db() as session:
        assert session.get(TelemetryRun, make_uuid(2001)) is None
        assert session.get(TelemetryRun, make_uuid(2002)) is None
        assert session.get(TelemetryRun, make_uuid(2003)) is not None
