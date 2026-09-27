"""Unit tests for TelemetryBatchV1 export and deterministic serialization (ADR-0003)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.models import TelemetryRun
from daily_agent.telemetry import exporter, finalizer, writer
from daily_agent.telemetry.events import SignalType, TelemetryBatchV1
from daily_agent.telemetry.sanitizer import SanitizationError
from tests.unit.telemetry.conftest import (
    build_synthetic_run_record,
    build_synthetic_signal_record,
    make_uuid,
)


def test_export_empty_returns_none(tmp_path: Path, temp_db: sessionmaker[Session]) -> None:
    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    with temp_db() as session:
        result = exporter.export_batch(
            session,
            out_dir=tmp_path / "exports",
            producer_version="0.1.0",
            now=now,
        )
        assert result is None


def test_export_batch_lifecycle_and_validation(
    tmp_path: Path, temp_db: sessionmaker[Session]
) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    export_dir = tmp_path / "exports"

    run = build_synthetic_run_record(
        run_id=make_uuid(501),
        request_fingerprint="f" * 64,
        started_at=t0,
        completed_at=t0,
    )

    with temp_db() as session:
        writer.persist_events(session, [run], now=t0, attribution_window_seconds=3600)
        session.commit()

    # Finalize the run
    with temp_db() as session:
        finalizer.finalize_run(session, make_uuid(501), now=t0 + timedelta(hours=1))
        session.commit()

    # Export
    with temp_db() as session:
        result = exporter.export_batch(
            session,
            out_dir=export_dir,
            producer_version="0.1.0",
            now=t0 + timedelta(hours=2),
        )
        session.commit()
        assert result is not None

    # Check files
    assert result.path.exists()
    sha_file = result.path.with_name(result.path.name + ".sha256")
    assert sha_file.exists()

    file_bytes = result.path.read_bytes()
    expected_sha = hashlib.sha256(file_bytes).hexdigest()
    assert expected_sha in sha_file.read_text(encoding="utf-8")

    # Validate against TelemetryBatchV1 contract
    parsed_json = json.loads(file_bytes.decode("utf-8"))
    batch_v1 = TelemetryBatchV1.model_validate(parsed_json)
    assert batch_v1.batch_id == result.batch_id
    assert len(batch_v1.runs) == 1

    # Verify request_fingerprint was NOT exported
    run_dump = batch_v1.runs[0].model_dump()
    assert "request_fingerprint" not in run_dump

    # Verify DB row is marked
    with temp_db() as session:
        run_row = session.get(TelemetryRun, make_uuid(501))
        assert run_row is not None
        assert run_row.export_batch_id == result.batch_id


def test_export_is_deterministic(tmp_path: Path, temp_db: sessionmaker[Session]) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    run1 = build_synthetic_run_record(run_id=make_uuid(601), started_at=t0, completed_at=t0)
    run2 = build_synthetic_run_record(run_id=make_uuid(602), started_at=t0, completed_at=t0)

    with temp_db() as session:
        writer.persist_events(session, [run1, run2], now=t0, attribution_window_seconds=3600)
        finalizer.finalize_run(session, make_uuid(601), now=t0)
        finalizer.finalize_run(session, make_uuid(602), now=t0)
        session.commit()

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    now = t0 + timedelta(hours=1)

    # First export
    with temp_db() as session:
        res1 = exporter.export_batch(session, out_dir=out1, producer_version="0.1.0", now=now)
        session.commit()
        assert res1 is not None

    # Unmark exported rows to simulate re-running export on the same data
    with temp_db() as session:
        for r_id in [make_uuid(601), make_uuid(602)]:
            row = session.get(TelemetryRun, r_id)
            assert row is not None
            row.export_batch_id = None
        session.commit()

    # Second export
    with temp_db() as session:
        res2 = exporter.export_batch(session, out_dir=out2, producer_version="0.1.0", now=now)
        session.commit()
        assert res2 is not None

    # Batch IDs and payload SHA must match identically
    assert res1.batch_id == res2.batch_id
    assert res1.payload_sha256 == res2.payload_sha256


def test_late_signals_exported_in_subsequent_batch(
    tmp_path: Path, temp_db: sessionmaker[Session]
) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    export_dir = tmp_path / "late_exports"

    run = build_synthetic_run_record(run_id=make_uuid(701), started_at=t0, completed_at=t0)

    with temp_db() as session:
        writer.persist_events(session, [run], now=t0, attribution_window_seconds=3600)
        finalizer.finalize_run(session, make_uuid(701), now=t0)
        session.commit()

    # Export initial run
    with temp_db() as session:
        res1 = exporter.export_batch(session, out_dir=export_dir, producer_version="0.1.0", now=t0)
        session.commit()
        assert res1 is not None
        assert res1.run_count == 1

    # Late signal arrives after run has been exported
    late_sig = build_synthetic_signal_record(
        run_id=make_uuid(701),
        signal_type=SignalType.CORRECTION,
        observed_at=t0 + timedelta(hours=5),
    )
    with temp_db() as session:
        writer.persist_events(session, [late_sig], now=t0 + timedelta(hours=5), attribution_window_seconds=3600)
        session.commit()

    # Second export: run is already exported, only late signal should be exported
    with temp_db() as session:
        res2 = exporter.export_batch(
            session,
            out_dir=export_dir,
            producer_version="0.1.0",
            now=t0 + timedelta(hours=6),
        )
        session.commit()
        assert res2 is not None
        assert res2.run_count == 0
        assert res2.signal_count == 1

    parsed = json.loads(res2.path.read_bytes().decode("utf-8"))
    assert len(parsed["runs"]) == 0
    assert len(parsed["late_signals"]) == 1
    assert parsed["late_signals"][0]["signal_id"] == late_sig.signal_id


def test_export_sanitization_failure_fails_closed(
    tmp_path: Path, temp_db: sessionmaker[Session]
) -> None:
    t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    export_dir = tmp_path / "fail_exports"

    run = build_synthetic_run_record(run_id=make_uuid(801), started_at=t0, completed_at=t0)

    with temp_db() as session:
        writer.persist_events(session, [run], now=t0, attribution_window_seconds=3600)
        finalizer.finalize_run(session, make_uuid(801), now=t0)
        # Corrupt DB row with an unredacted secret in live_fallback_reason
        run_row = session.get(TelemetryRun, make_uuid(801))
        assert run_row is not None
        run_row.live_fallback_reason = "sk-live-1234567890abcdef1234567890"
        session.commit()
    with temp_db() as session, pytest.raises(SanitizationError):
        exporter.export_batch(session, out_dir=export_dir, producer_version="0.1.0", now=t0)

    # Verify no file was written
    assert not export_dir.exists() or len(list(export_dir.glob("*.json"))) == 0

    # Verify row was NOT marked
    with temp_db() as session:
        run_row = session.get(TelemetryRun, make_uuid(801))
        assert run_row is not None
        assert run_row.export_batch_id is None
