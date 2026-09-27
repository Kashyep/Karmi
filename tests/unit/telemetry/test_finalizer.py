"""Unit tests for telemetry outcome finalization (ADR-0003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from daily_agent.models import TelemetryOutcomeSignal, TelemetryRunOutcome
from daily_agent.telemetry import finalizer, writer
from daily_agent.telemetry.events import (
    FeedbackType,
    SignalSource,
    SignalStrength,
    SignalType,
)
from tests.unit.telemetry.conftest import (
    build_synthetic_feedback_record,
    build_synthetic_run_record,
    build_synthetic_signal_record,
    make_hex64,
    make_uuid,
)


def test_finalize_due_respects_attribution_window(temp_db: sessionmaker[Session]) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    window = 3600  # 1 hour

    # Run 1: completed 2 hours ago (eligible)
    run1 = build_synthetic_run_record(
        run_id=make_uuid(101),
        started_at=t0 - timedelta(hours=2),
        completed_at=t0 - timedelta(hours=2),
    )
    # Run 2: completed 10 minutes ago (not eligible)
    run2 = build_synthetic_run_record(
        run_id=make_uuid(102),
        started_at=t0 - timedelta(minutes=10),
        completed_at=t0 - timedelta(minutes=10),
    )

    with temp_db() as session:
        writer.persist_events(session, [run1, run2], now=t0, attribution_window_seconds=window)
        session.commit()

    with temp_db() as session:
        count = finalizer.finalize_due(session, now=t0, window_seconds=window)
        session.commit()
        assert count == 1

    with temp_db() as session:
        out1 = session.get(TelemetryRunOutcome, make_uuid(101))
        assert out1 is not None
        assert out1.finalized_at is not None
        assert out1.finalized_at.replace(tzinfo=UTC) == t0
        out2 = session.get(TelemetryRunOutcome, make_uuid(102))
        assert out2 is not None
        assert out2.finalized_at is None


def test_finalize_aggregates_signals_and_correction_distance(
    temp_db: sessionmaker[Session],
) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    run = build_synthetic_run_record(run_id=make_uuid(201), started_at=t0, completed_at=t0)
    sig_retry = build_synthetic_signal_record(
        run_id=make_uuid(201),
        signal_type=SignalType.RETRY,
        strength=SignalStrength.WEAK,
        source=SignalSource.DERIVED,
    )
    sig_accept = build_synthetic_signal_record(
        run_id=make_uuid(201),
        signal_type=SignalType.ACCEPT,
        strength=SignalStrength.STRONG,
        source=SignalSource.EXPLICIT_FEEDBACK,
    )
    fb_corr = build_synthetic_feedback_record(
        run_id=make_uuid(201),
        feedback_type=FeedbackType.CORRECTION,
        correction_distance=0.25,
        created_at=t0 + timedelta(minutes=5),
    )

    with temp_db() as session:
        writer.persist_events(session, [run, sig_retry, sig_accept, fb_corr], now=t0, attribution_window_seconds=3600)
        session.commit()

    now = t0 + timedelta(hours=2)
    with temp_db() as session:
        ok = finalizer.finalize_run(session, make_uuid(201), now=now)
        session.commit()
        assert ok is True

    with temp_db() as session:
        out = session.get(TelemetryRunOutcome, make_uuid(201))
        assert out is not None
        assert out.finalized_at is not None
        assert out.finalized_at.replace(tzinfo=UTC) == now
        assert out.user_retry_signal is True
        assert out.user_accept_signal is True
        assert out.user_correction_signal is True  # From feedback-generated signal
        assert out.correction_distance == 0.25


def test_abandonment_only_for_ask_user_without_followup(temp_db: sessionmaker[Session]) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    actor1 = make_hex64("1")
    actor2 = make_hex64("2")
    actor3 = make_hex64("3")
    window = 3600

    # Case 1: ASK_USER with no followup -> abandon=True
    run_ask_abandon = build_synthetic_run_record(
        run_id=make_uuid(301),
        anonymous_actor_id=actor1,
        outcome_str="ASK_USER",
        started_at=t0 - timedelta(hours=2),
        completed_at=t0 - timedelta(hours=2),
    )

    # Case 2: ASK_USER with followup run within window -> abandon=False
    run_ask_with_followup = build_synthetic_run_record(
        run_id=make_uuid(302),
        anonymous_actor_id=actor2,
        outcome_str="ASK_USER",
        started_at=t0 - timedelta(hours=2),
        completed_at=t0 - timedelta(hours=2),
    )
    followup_run = build_synthetic_run_record(
        run_id=make_uuid(303),
        anonymous_actor_id=actor2,
        started_at=t0 - timedelta(hours=1, minutes=30),
        completed_at=t0 - timedelta(hours=1, minutes=30),
    )

    # Case 3: Other outcome (e.g. STORE_MEMORY) without followup -> abandon=False
    run_other_no_followup = build_synthetic_run_record(
        run_id=make_uuid(304),
        anonymous_actor_id=actor3,
        outcome_str="STORE_MEMORY",
        started_at=t0 - timedelta(hours=2),
        completed_at=t0 - timedelta(hours=2),
    )

    with temp_db() as session:
        writer.persist_events(
            session,
            [run_ask_abandon, run_ask_with_followup, followup_run, run_other_no_followup],
            now=t0,
            attribution_window_seconds=window,
        )
        session.commit()

    with temp_db() as session:
        finalizer.finalize_due(session, now=t0, window_seconds=window)
        session.commit()

    with temp_db() as session:
        out1 = session.get(TelemetryRunOutcome, make_uuid(301))
        assert out1 is not None
        assert out1.user_abandon_signal is True

        # Weak derived no_followup_after_ask signal inserted
        sig = session.scalar(
            TelemetryOutcomeSignal.__table__.select().where(
                TelemetryOutcomeSignal.run_id == make_uuid(301),
                TelemetryOutcomeSignal.signal_type == "no_followup_after_ask",
            )
        )
        assert sig is not None

        out2 = session.get(TelemetryRunOutcome, make_uuid(302))
        assert out2 is not None
        assert out2.user_abandon_signal is False

        out3 = session.get(TelemetryRunOutcome, make_uuid(304))
        assert out3 is not None
        assert out3.user_abandon_signal is False
