"""Non-blocking telemetry collector with bounded memory and local spooling (ADR-0003).

Provides the TelemetryCollector background worker and the NullCollector no-op sink.
The emit() path is strictly non-blocking: mandatory events are appended to a JSONL
spool file on disk if the in-memory queue is full, and replayed into the database
once connectivity is restored.
"""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from daily_agent.models import utcnow
from daily_agent.observability import METRICS, Metrics
from daily_agent.telemetry import finalizer, writer
from daily_agent.telemetry.events import (
    Priority,
    TelemetryEvent,
    priority_of,
)

logger = logging.getLogger(__name__)
_event_adapter: TypeAdapter[TelemetryEvent] = TypeAdapter(TelemetryEvent)


class TelemetrySink(Protocol):
    """Protocol for recording telemetry events."""

    def emit(self, event: TelemetryEvent) -> None:
        """Enqueue or spool a telemetry event. Never raises or blocks."""
        ...

    def start(self) -> None:
        """Start background processing."""
        ...

    def stop(self, timeout: float = 5.0) -> None:
        """Stop background worker and flush or spool pending items."""
        ...

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until all items emitted prior to the call are persisted or spooled."""
        ...

    def health(self) -> dict[str, object]:
        """Return operational health indicators."""
        ...


class NullCollector:
    """No-op sink when telemetry is disabled."""

    def emit(self, event: TelemetryEvent) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self, timeout: float = 5.0) -> None:
        pass

    def flush(self, timeout: float = 5.0) -> bool:
        return True

    def health(self) -> dict[str, object]:
        return {"enabled": False}


class TelemetryCollector:
    """Threaded collector draining bounded queues into sync SQLAlchemy storage."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        queue_size: int,
        batch_size: int,
        flush_interval_seconds: float,
        spool_path: Path,
        attribution_window_seconds: int,
        finalize_interval_seconds: float = 30.0,
        metrics: Metrics = METRICS,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._queue_size = queue_size
        self._batch_size = batch_size
        self._flush_interval_seconds = flush_interval_seconds
        self._spool_path = spool_path
        self._attribution_window_seconds = attribution_window_seconds
        self._finalize_interval_seconds = finalize_interval_seconds
        self._metrics = metrics
        self._clock = clock

        self._queue: queue.Queue[TelemetryEvent] = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._spool_lock = threading.Lock()

        self._cond = threading.Condition()
        self._emitted_count = 0
        self._persisted_count = 0
        self._oldest_unwritten_ts: float | None = None

        self._in_memory_batch: list[TelemetryEvent] = []
        self._backoff_delay = 1.0
        self._max_backoff = 30.0
        self._last_finalize_time = 0.0

    def start(self) -> None:
        """Start the background writer thread (idempotent)."""
        with self._lifecycle_lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._writer_loop,
                name="telemetry-writer",
                daemon=True,
            )
            self._thread.start()

    def emit(self, event: TelemetryEvent) -> None:
        """Emit an event. Never blocks the caller, touches the DB, or raises."""
        try:
            pri = priority_of(event)
            q_depth = self._queue.qsize()

            # Optional events dropped when queue >= 80% full
            if pri == Priority.OPTIONAL and (q_depth / self._queue_size >= 0.8):
                self._metrics.inc("telemetry_dropped_optional_total")
                return

            try:
                self._queue.put_nowait(event)
                with self._cond:
                    self._emitted_count += 1
                    if self._oldest_unwritten_ts is None:
                        self._oldest_unwritten_ts = time.monotonic()
            except queue.Full:
                if pri == Priority.MANDATORY:
                    self._append_to_spool(event)
                    self._metrics.inc("telemetry_spooled_total")
                    with self._cond:
                        self._emitted_count += 1
                        self._persisted_count += 1
                        self._cond.notify_all()
                else:
                    self._metrics.inc("telemetry_dropped_optional_total")

            self._metrics.set_gauge("telemetry_queue_depth", float(self._queue.qsize()))
        except Exception as exc:
            # emit must NEVER raise under any circumstance
            logger.debug("telemetry emit encountered unexpected error: %s", exc)

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until all items emitted prior to the call are persisted or spooled."""
        with self._cond:
            target = self._emitted_count
            if self._persisted_count >= target:
                return True
            deadline = time.monotonic() + timeout
            while self._persisted_count < target:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return self._persisted_count >= target

    def stop(self, timeout: float = 5.0) -> None:
        """Stop writer thread and persist or spool any remaining events (idempotent)."""
        with self._lifecycle_lock:
            if not self._running:
                return
            self._running = False

        # Attempt to flush before signaling stop
        self.flush(timeout=min(1.0, timeout / 2))
        self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(0.5, timeout / 2))

        # Drain any leftovers in memory or queue to disk spool
        leftovers: list[TelemetryEvent] = list(self._in_memory_batch)
        self._in_memory_batch.clear()

        while not self._queue.empty():
            try:
                leftovers.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if leftovers:
            self._spool_batch(leftovers)
            with self._cond:
                self._persisted_count += len(leftovers)
                self._cond.notify_all()

    def health(self) -> dict[str, object]:
        """Return operational health snapshot."""
        return {
            "enabled": True,
            "running": self._running,
            "queue_depth": self._queue.qsize(),
            "spool_exists": self._spool_path.exists(),
            "last_flush_ms": self._metrics.gauge("telemetry_last_flush_ms"),
            "dropped_optional": self._metrics.counter("telemetry_dropped_optional_total"),
            "spooled_mandatory": self._metrics.counter("telemetry_spooled_total"),
            "write_failures": self._metrics.counter("telemetry_write_failures_total"),
        }

    def _writer_loop(self) -> None:
        """Background thread draining queues and persisting events."""
        # Initial spool replay on startup
        self._replay_spool_if_any()

        while not self._stop_event.is_set() or not self._queue.empty() or self._in_memory_batch:
            batch: list[TelemetryEvent] = []
            if self._in_memory_batch:
                batch = self._in_memory_batch
            else:
                # Coalesce until the batch fills or its flush deadline expires. Writing
                # one DB transaction per event contends with foreground budget commits
                # (especially SQLite development/test databases).
                try:
                    batch.append(self._queue.get(timeout=self._flush_interval_seconds))
                    deadline = time.monotonic() + self._flush_interval_seconds
                    while len(batch) < self._batch_size and not self._stop_event.is_set():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        try:
                            batch.append(self._queue.get(timeout=remaining))
                        except queue.Empty:
                            break
                except queue.Empty:
                    pass
            # Update gauges
            self._update_gauges()

            if not batch:
                self._replay_spool_if_any()
                self._run_finalize_if_due()
                continue

            # Attempt DB write
            t0 = time.perf_counter()
            write_ok = False
            try:
                with self._session_factory() as session:
                    writer.persist_events(
                        session,
                        batch,
                        now=self._clock(),
                        attribution_window_seconds=self._attribution_window_seconds,
                    )
                    session.commit()
                write_ok = True
            except Exception:
                self._metrics.inc("telemetry_write_failures_total")
                if self._stop_event.is_set():
                    self._spool_batch(batch)
                    self._in_memory_batch.clear()
                    with self._cond:
                        self._persisted_count += len(batch)
                        self._cond.notify_all()
                    break
                else:
                    self._in_memory_batch = batch
                    self._stop_event.wait(self._backoff_delay)
                    self._backoff_delay = min(self._max_backoff, self._backoff_delay * 2)
                    continue

            if write_ok:
                self._in_memory_batch = []
                self._backoff_delay = 1.0
                flush_ms = (time.perf_counter() - t0) * 1000
                self._metrics.set_gauge("telemetry_last_flush_ms", flush_ms)

                with self._cond:
                    self._persisted_count += len(batch)
                    if self._queue.empty():
                        self._oldest_unwritten_ts = None
                    else:
                        self._oldest_unwritten_ts = time.monotonic()
                    self._cond.notify_all()

                self._replay_spool_if_any()
                self._run_finalize_if_due()

    def _append_to_spool(self, event: TelemetryEvent) -> None:
        with self._spool_lock:
            self._spool_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._spool_path, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")

    def _spool_batch(self, events: Sequence[TelemetryEvent]) -> None:
        if not events:
            return
        with self._spool_lock:
            self._spool_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._spool_path, "a", encoding="utf-8") as f:
                for event in events:
                    f.write(event.model_dump_json() + "\n")

    def _replay_spool_if_any(self) -> None:
        replaying_path = self._spool_path.with_name(self._spool_path.name + ".replaying")
        while True:
            with self._spool_lock:
                if not replaying_path.exists():
                    if self._spool_path.exists() and self._spool_path.stat().st_size > 0:
                        try:
                            os.replace(self._spool_path, replaying_path)
                        except OSError:
                            return
                    else:
                        return

            if not replaying_path.exists():
                return

            replay_batch: list[TelemetryEvent] = []
            rejected_lines: list[str] = []

            try:
                with open(replaying_path, encoding="utf-8") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            evt = _event_adapter.validate_json(line_str)
                            replay_batch.append(evt)
                        except Exception:
                            rejected_lines.append(line_str)
                            self._metrics.inc("telemetry_spool_rejected_total")
            except Exception:
                return

            if rejected_lines:
                rejected_path = self._spool_path.with_name(self._spool_path.name + ".rejected")
                with contextlib.suppress(OSError), open(rejected_path, "a", encoding="utf-8") as rf:
                    for r_line in rejected_lines:
                        rf.write(r_line + "\n")

            if replay_batch:
                try:
                    with self._session_factory() as session:
                        writer.persist_events(
                            session,
                            replay_batch,
                            now=self._clock(),
                            attribution_window_seconds=self._attribution_window_seconds,
                        )
                        session.commit()
                except Exception:
                    # Keep replaying file so next cycle retries
                    return

            # Success: remove the replaying file
            with contextlib.suppress(OSError):
                replaying_path.unlink(missing_ok=True)
    def _run_finalize_if_due(self) -> None:
        now_mono = time.monotonic()
        if now_mono - self._last_finalize_time >= self._finalize_interval_seconds:
            try:
                with self._session_factory() as session:
                    finalizer.finalize_due(
                        session,
                        now=self._clock(),
                        window_seconds=self._attribution_window_seconds,
                    )
                    session.commit()
                self._last_finalize_time = now_mono
            except Exception as exc:
                logger.debug("telemetry finalize_due encountered error: %s", exc)

    def _update_gauges(self) -> None:
        q_size = self._queue.qsize()
        self._metrics.set_gauge("telemetry_queue_depth", float(q_size))
        if self._oldest_unwritten_ts is not None and (q_size > 0 or self._in_memory_batch):
            age = max(0.0, time.monotonic() - self._oldest_unwritten_ts)
        else:
            age = 0.0
        self._metrics.set_gauge("telemetry_oldest_unwritten_age_s", age)
