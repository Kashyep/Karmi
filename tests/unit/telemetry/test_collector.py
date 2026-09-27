"""Unit tests for the non-blocking TelemetryCollector and local spooling (ADR-0003)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from daily_agent.models import TelemetryRun
from daily_agent.observability import Metrics
from daily_agent.telemetry.collector import NullCollector, TelemetryCollector
from tests.unit.telemetry.conftest import (
    build_synthetic_ops_event,
    build_synthetic_run_record,
    make_uuid,
)


def test_null_collector() -> None:
    null_sink = NullCollector()
    run = build_synthetic_run_record()
    null_sink.emit(run)
    null_sink.start()
    assert null_sink.flush() is True
    null_sink.stop()
    assert null_sink.health() == {"enabled": False}


def test_emit_latency_under_simulated_db_outage(
    tmp_path: Path,
) -> None:
    metrics = Metrics()

    def failing_session_factory() -> Any:
        raise ConnectionRefusedError("Simulated database outage")

    collector = TelemetryCollector(
        session_factory=failing_session_factory,
        queue_size=100,
        batch_size=10,
        flush_interval_seconds=0.05,
        spool_path=tmp_path / "spool.jsonl",
        attribution_window_seconds=3600,
        metrics=metrics,
    )
    collector.start()

    # Measure emit latency under simulated DB failure
    latencies: list[float] = []
    for i in range(20):
        evt = build_synthetic_run_record(run_id=make_uuid(i + 1))
        t0 = time.perf_counter()
        collector.emit(evt)
        latencies.append(time.perf_counter() - t0)

    collector.stop(timeout=1.0)

    # Average and maximum emit latencies
    avg_latency_ms = (sum(latencies) / len(latencies)) * 1000
    max_latency_ms = max(latencies) * 1000

    # emit() must never block the request thread: latency under 10ms
    assert max_latency_ms < 20.0, f"Max emit latency exceeded 20ms: {max_latency_ms:.2f}ms"
    assert avg_latency_ms < 5.0, f"Avg emit latency exceeded 5ms: {avg_latency_ms:.2f}ms"


def test_optional_events_dropped_under_backpressure(tmp_path: Path) -> None:
    metrics = Metrics()
    # Writer thread not started so queue builds up
    def dummy_session_factory() -> Any:
        return None

    collector = TelemetryCollector(
        session_factory=dummy_session_factory,
        queue_size=10,
        batch_size=5,
        flush_interval_seconds=1.0,
        spool_path=tmp_path / "spool.jsonl",
        attribution_window_seconds=3600,
        metrics=metrics,
    )

    # Fill queue to 8 items (80% of 10)
    for i in range(8):
        collector.emit(build_synthetic_run_record(run_id=make_uuid(100 + i)))

    assert collector.health()["queue_depth"] == 8

    # 9th event: optional ops event -> should be dropped because queue is >= 80% full
    collector.emit(build_synthetic_ops_event(event_id=make_uuid(999)))
    assert metrics.counter("telemetry_dropped_optional_total") == 1
    assert collector.health()["queue_depth"] == 8


def test_mandatory_events_spill_to_spool_and_replay_on_recovery(
    tmp_path: Path, temp_db: sessionmaker[Session]
) -> None:
    metrics = Metrics()
    spool_path = tmp_path / "spool.jsonl"

    # Start collector with queue size 2 and broken DB to force queue fill
    def broken_db() -> Any:
        raise RuntimeError("DB is down")

    collector = TelemetryCollector(
        session_factory=broken_db,
        queue_size=2,
        batch_size=2,
        flush_interval_seconds=0.05,
        spool_path=spool_path,
        attribution_window_seconds=3600,
        metrics=metrics,
    )
    # Emit 2 events (fills queue) + 2 more (must spill to spool)
    for i in range(4):
        collector.emit(build_synthetic_run_record(run_id=make_uuid(200 + i)))

    collector.start()
    collector.stop(timeout=1.0)

    # Spool must have received the spilled mandatory events
    assert spool_path.exists()
    assert metrics.counter("telemetry_spooled_total") >= 2

    # Now recover: start a fresh collector with real DB using the same spool
    recovered_collector = TelemetryCollector(
        session_factory=temp_db,
        queue_size=10,
        batch_size=10,
        flush_interval_seconds=0.05,
        spool_path=spool_path,
        attribution_window_seconds=3600,
        metrics=metrics,
    )
    recovered_collector.start()
    assert recovered_collector.flush(timeout=2.0) is True
    recovered_collector.stop(timeout=1.0)

    # Check that events from spool were persisted in temp_db without duplicates
    with temp_db() as session:
        for i in range(4):
            assert session.get(TelemetryRun, make_uuid(200 + i)) is not None


def test_spool_replay_idempotency(tmp_path: Path, temp_db: sessionmaker[Session]) -> None:
    metrics = Metrics()
    spool_path = tmp_path / "spool.jsonl"

    run = build_synthetic_run_record(run_id=make_uuid(301))
    spool_path.write_text(run.model_dump_json() + "\n", encoding="utf-8")

    collector = TelemetryCollector(
        session_factory=temp_db,
        queue_size=10,
        batch_size=10,
        flush_interval_seconds=0.05,
        spool_path=spool_path,
        attribution_window_seconds=3600,
        metrics=metrics,
    )
    collector.start()
    assert collector.flush(timeout=2.0) is True
    collector.stop(timeout=1.0)

    with temp_db() as session:
        assert session.get(TelemetryRun, make_uuid(301)) is not None

    # Re-write the same event to spool and replay again
    spool_path.write_text(run.model_dump_json() + "\n", encoding="utf-8")
    collector2 = TelemetryCollector(
        session_factory=temp_db,
        queue_size=10,
        batch_size=10,
        flush_interval_seconds=0.05,
        spool_path=spool_path,
        attribution_window_seconds=3600,
        metrics=metrics,
    )
    collector2.start()
    assert collector2.flush(timeout=2.0) is True
    collector2.stop(timeout=1.0)

    # Must still exist once with no error
    with temp_db() as session:
        assert session.get(TelemetryRun, make_uuid(301)) is not None
