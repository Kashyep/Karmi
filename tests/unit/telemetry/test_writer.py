"""Unit tests for database persistence of telemetry records (ADR-0003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

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
from daily_agent.telemetry import writer
from daily_agent.telemetry.events import FeedbackType, SignalSource, SignalStrength, SignalType
from tests.unit.telemetry.conftest import (
    build_synthetic_feedback_record,
    build_synthetic_ops_event,
    build_synthetic_run_record,
    build_synthetic_signal_record,
    make_hex64,
    make_uuid,
)


def test_persist_run_record_populates_all_tables(temp_db: sessionmaker[Session]) -> None:
    now = datetime(2026, 9, 27, 10, 0, 5, tzinfo=UTC)
    run_record = build_synthetic_run_record(run_id=make_uuid(10))

    with temp_db() as session:
        writer.persist_events(
            session,
            [run_record],
            now=now,
            attribution_window_seconds=86_400,
        )
        session.commit()

    with temp_db() as session:
        run_row = session.get(TelemetryRun, make_uuid(10))
        assert run_row is not None
        assert run_row.status == "completed"
        assert run_row.tier == "ananta"

        decisions = list(
            session.scalars(
                select(TelemetryRouterDecision).where(TelemetryRouterDecision.run_id == make_uuid(10))
            ).all()
        )
        assert len(decisions) == 1
        assert decisions[0].selected_model == "fake-economy"

        attempts = list(
            session.scalars(
                select(TelemetryModelAttempt).where(TelemetryModelAttempt.run_id == make_uuid(10))
            ).all()
        )
        assert len(attempts) == 1
        assert attempts[0].latency_ms == 120

        tools = list(
            session.scalars(
                select(TelemetryToolEvent).where(TelemetryToolEvent.run_id == make_uuid(10))
            ).all()
        )
        assert len(tools) == 1
        assert tools[0].tool_name == "store_memory"

        outcome = session.get(TelemetryRunOutcome, make_uuid(10))
        assert outcome is not None
        assert outcome.completed is True
        assert outcome.finalized_at is None
        assert outcome.user_retry_signal is False


def test_persist_run_record_is_idempotent(temp_db: sessionmaker[Session]) -> None:
    now = datetime(2026, 9, 27, 10, 0, 5, tzinfo=UTC)
    run_record = build_synthetic_run_record(run_id=make_uuid(20))

    with temp_db() as session:
        writer.persist_events(session, [run_record], now=now, attribution_window_seconds=86_400)
        session.commit()

    # Persist again - must not raise duplicate key error
    with temp_db() as session:
        writer.persist_events(session, [run_record], now=now, attribution_window_seconds=86_400)
        session.commit()

    with temp_db() as session:
        count = len(
            list(session.scalars(select(TelemetryRun).where(TelemetryRun.run_id == make_uuid(20))).all())
        )
        assert count == 1


def test_derived_retry_signal_generation(temp_db: sessionmaker[Session]) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 9, 27, 10, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 9, 27, 10, 0, 30, tzinfo=UTC)
    t3 = datetime(2026, 9, 27, 10, 0, 31, tzinfo=UTC)
    actor = make_hex64("9")
    fingerprint = make_hex64("f")

    run1 = build_synthetic_run_record(
        run_id=make_uuid(31),
        anonymous_actor_id=actor,
        request_fingerprint=fingerprint,
        started_at=t0,
        completed_at=t1,
    )
    run2 = build_synthetic_run_record(
        run_id=make_uuid(32),
        anonymous_actor_id=actor,
        request_fingerprint=fingerprint,
        started_at=t2,
        completed_at=t3,
    )

    with temp_db() as session:
        writer.persist_events(session, [run1], now=t1, attribution_window_seconds=86_400)
        session.commit()

    with temp_db() as session:
        writer.persist_events(session, [run2], now=t3, attribution_window_seconds=86_400)
        session.commit()

    # run1 should now have a derived retry signal
    with temp_db() as session:
        signals = list(
            session.scalars(
                select(TelemetryOutcomeSignal).where(TelemetryOutcomeSignal.run_id == make_uuid(31))
            ).all()
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == SignalType.RETRY.value
        assert sig.strength == SignalStrength.WEAK.value
        assert sig.confidence == 0.6
        assert sig.source == SignalSource.DERIVED.value
        assert sig.late is False


def test_feedback_persists_and_emits_matching_explicit_signal(
    temp_db: sessionmaker[Session],
) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    run = build_synthetic_run_record(run_id=make_uuid(40), started_at=t0, completed_at=t0)

    with temp_db() as session:
        writer.persist_events(session, [run], now=t0, attribution_window_seconds=86_400)
        session.commit()

    feedback = build_synthetic_feedback_record(
        run_id=make_uuid(40),
        feedback_type=FeedbackType.ACCEPT,
        created_at=t0 + timedelta(seconds=10),
    )

    with temp_db() as session:
        writer.persist_events(session, [feedback], now=t0 + timedelta(seconds=10), attribution_window_seconds=86_400)
        session.commit()

    with temp_db() as session:
        fb_row = session.get(TelemetryFeedback, feedback.feedback_id)
        assert fb_row is not None
        assert fb_row.feedback_type == "accept"

        # Matching strong explicit signal
        sig_rows = list(
            session.scalars(
                select(TelemetryOutcomeSignal).where(
                    TelemetryOutcomeSignal.run_id == make_uuid(40),
                    TelemetryOutcomeSignal.signal_type == "accept",
                )
            ).all()
        )
        assert len(sig_rows) == 1
        assert sig_rows[0].strength == "strong"
        assert sig_rows[0].confidence == 1.0
        assert sig_rows[0].source == "explicit_feedback"
        assert sig_rows[0].late is False


def test_late_flag_when_parent_run_is_exported(temp_db: sessionmaker[Session]) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    run = build_synthetic_run_record(run_id=make_uuid(50), started_at=t0, completed_at=t0)

    with temp_db() as session:
        writer.persist_events(session, [run], now=t0, attribution_window_seconds=86_400)
        # Simulate that run has already been exported
        run_row = session.get(TelemetryRun, make_uuid(50))
        assert run_row is not None
        run_row.export_batch_id = make_hex64("e")
        session.commit()

    # Now add a signal for this already exported run
    sig = build_synthetic_signal_record(
        run_id=make_uuid(50),
        signal_type=SignalType.CORRECTION,
        observed_at=t0 + timedelta(hours=2),
    )

    with temp_db() as session:
        writer.persist_events(session, [sig], now=t0 + timedelta(hours=2), attribution_window_seconds=86_400)
        session.commit()

    with temp_db() as session:
        sig_row = session.get(TelemetryOutcomeSignal, sig.signal_id)
        assert sig_row is not None
        assert sig_row.late is True


def test_persist_ops_event(temp_db: sessionmaker[Session]) -> None:
    now = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    ops = build_synthetic_ops_event(event_id=make_uuid(60), event_type="test_event")

    with temp_db() as session:
        writer.persist_events(session, [ops], now=now, attribution_window_seconds=86_400)
        session.commit()

    with temp_db() as session:
        row = session.get(TelemetryOpsEvent, make_uuid(60))
        assert row is not None
        assert row.event_type == "test_event"
