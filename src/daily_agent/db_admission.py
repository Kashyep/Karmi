"""Process-level admission control for database sessions.

Each engine carries a bounded slot count equal to its pool capacity (``pool_size + max_overflow``).
A request session takes one slot for its lifetime and gives it back when closed. Requests that
find no free slot wait up to ``database_admission_wait_seconds`` and then fail with
:class:`DatabaseBusy`, which the API maps to ``503`` with ``Retry-After``. Waiting here, instead of
inside SQLAlchemy's pool, keeps the pool from ever timing out (which surfaced as ``500``).

The primitive is a ``threading`` semaphore because request handlers are synchronous and run in
worker threads; the event loop never acquires a slot (see ``streaming/runner.py``).

Streaming responses must release their session before the first byte is sent: see
``release_session`` and its call sites in ``routes/stream.py``.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

LEASE_KEY = "daily_agent.db_lease"

# Background DB sections (stream flushes, heartbeats, settlement) wait longer than requests:
# failing one of them fails a healthy stream, so they only give up after a long bound.
RUNNER_WAIT_SECONDS = 60.0
DEFAULT_CAPACITY = 20
DEFAULT_WAIT_SECONDS = 10.0

_ADMISSIONS: weakref.WeakKeyDictionary[Engine, DatabaseAdmission] = weakref.WeakKeyDictionary()


class DatabaseBusy(Exception):
    """No database slot became free within the admission wait."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__("database capacity busy; retry shortly")
        self.retry_after_s = retry_after_s


class DatabaseAdmission:
    def __init__(self, capacity: int, wait_seconds: float) -> None:
        if capacity < 1:
            raise ValueError("admission capacity must be at least 1")
        self.capacity = capacity
        self.wait_seconds = wait_seconds
        self._slots = threading.BoundedSemaphore(capacity)

    def acquire(self, wait_seconds: float | None = None) -> None:
        wait = self.wait_seconds if wait_seconds is None else wait_seconds
        if not self._slots.acquire(timeout=wait):
            raise DatabaseBusy(retry_after_s=max(1, int(self.wait_seconds)))

    def release(self) -> None:
        self._slots.release()


class SessionLease:
    """One admission slot held by one session. Releasing twice is a no-op."""

    def __init__(self, admission: DatabaseAdmission) -> None:
        self._admission = admission
        self._held = True
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if not self._held:
                return
            self._held = False
        self._admission.release()


def install_admission(engine: Engine, *, capacity: int, wait_seconds: float) -> None:
    _ADMISSIONS[engine] = DatabaseAdmission(capacity=capacity, wait_seconds=wait_seconds)


def _engine_of(bind: object) -> Engine | None:
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    return None


def _admission_for(engine: Engine) -> DatabaseAdmission:
    admission = _ADMISSIONS.get(engine)
    if admission is None:
        admission = DatabaseAdmission(capacity=DEFAULT_CAPACITY, wait_seconds=DEFAULT_WAIT_SECONDS)
        _ADMISSIONS[engine] = admission
    return admission


def acquire_session_lease(engine: Engine, wait_seconds: float | None = None) -> SessionLease:
    admission = _admission_for(engine)
    admission.acquire(wait_seconds)
    return SessionLease(admission)


def attach_lease(session: Session, lease: SessionLease) -> None:
    session.info[LEASE_KEY] = lease


def release_session(session: Session) -> None:
    """Close the session (returning its connection) and free its admission slot."""
    session.close()
    lease: Any = session.info.pop(LEASE_KEY, None)
    if lease is not None:
        lease.release()


@contextmanager
def leased_session(factory: Callable[[], Session]) -> Iterator[Session]:
    """Open a short background session under admission control, closed on exit."""
    bind = getattr(factory, "kw", {}).get("bind")
    engine = _engine_of(bind)
    if engine is None:
        with factory() as session:
            yield session
        return
    lease = acquire_session_lease(engine, RUNNER_WAIT_SECONDS)
    session = factory()
    attach_lease(session, lease)
    try:
        yield session
    finally:
        release_session(session)
