"""Process-level admission control for database sessions.

Each engine carries a bounded slot count equal to its pool capacity (``pool_size + max_overflow``).
A request session takes one slot for its lifetime and gives it back when closed. Requests that
find no free slot wait up to ``database_admission_wait_seconds`` and then fail with
:class:`DatabaseBusy`, which the API maps to ``503`` with ``Retry-After``. Waiting here, instead of
inside SQLAlchemy's pool, keeps the pool from ever timing out (which surfaced as ``500``).

Waiters queue FIFO and a released slot is handed directly to the oldest waiter, so a slot is
never lost to a race. Request sessions wait with :meth:`DatabaseAdmission.acquire_async`, which
parks the coroutine on the event loop and holds NO worker thread. A blocking wait would occupy one
of AnyIO's default 40 worker threads per waiter; the admitted holders need those threads to finish
their handlers and release, so a burst of waiters would starve the very requests they wait on.
Background sections (stream runner) run in threads and use the blocking :meth:`acquire`; the
runner acquires their slot on the loop first (see ``streaming/runner.py``).

Streaming responses must release their session before the first byte is sent: see
``release_session`` and its call sites in ``routes/stream.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import weakref
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
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

# A slot the caller already acquired on the event loop for the thread it is about to run in.
_PRE_ACQUIRED: ContextVar[SessionLease | None] = ContextVar("db_pre_acquired_lease", default=None)


class DatabaseBusy(Exception):
    """No database slot became free within the admission wait."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__("database capacity busy; retry shortly")
        self.retry_after_s = retry_after_s


class _Waiter:
    __slots__ = ("granted", "wake")

    def __init__(self, wake: Callable[[], None]) -> None:
        self.granted = False
        self.wake = wake


def _resolve(fut: asyncio.Future[None]) -> None:
    if not fut.done():
        fut.set_result(None)


class DatabaseAdmission:
    def __init__(self, capacity: int, wait_seconds: float) -> None:
        if capacity < 1:
            raise ValueError("admission capacity must be at least 1")
        self.capacity = capacity
        self.wait_seconds = wait_seconds
        self._lock = threading.Lock()
        self._free = capacity
        self._waiters: deque[_Waiter] = deque()

    def _release_locked(self) -> None:
        if self._waiters:
            waiter = self._waiters.popleft()
            waiter.granted = True
            waiter.wake()
        else:
            self._free += 1

    def _busy(self) -> DatabaseBusy:
        return DatabaseBusy(retry_after_s=max(1, int(self.wait_seconds)))

    def acquire(self, wait_seconds: float | None = None) -> None:
        """Blocking acquire for threads. Do not call on the event loop."""
        wait = self.wait_seconds if wait_seconds is None else wait_seconds
        done = threading.Event()
        waiter = _Waiter(done.set)
        with self._lock:
            if self._free > 0 and not self._waiters:
                self._free -= 1
                return
            self._waiters.append(waiter)
        if done.wait(wait):
            return
        with self._lock:
            if waiter.granted:
                return
            self._waiters.remove(waiter)
        raise self._busy()

    async def acquire_async(self, wait_seconds: float | None = None) -> None:
        """Acquire from a coroutine without holding a worker thread while waiting."""
        wait = self.wait_seconds if wait_seconds is None else wait_seconds
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()

        def wake() -> None:
            # Called under ``self._lock`` from any thread; the loop may already be closed.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_resolve, fut)

        waiter = _Waiter(wake)
        with self._lock:
            if self._free > 0 and not self._waiters:
                self._free -= 1
                return
            self._waiters.append(waiter)
        try:
            await asyncio.wait_for(fut, timeout=wait)
        except TimeoutError:
            with self._lock:
                if waiter.granted:
                    return
                self._waiters.remove(waiter)
            raise self._busy() from None
        except asyncio.CancelledError:
            with self._lock:
                if waiter.granted:
                    self._release_locked()
                else:
                    self._waiters.remove(waiter)
            raise

    def release(self) -> None:
        with self._lock:
            self._release_locked()


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


async def acquire_session_lease_async(
    engine: Engine, wait_seconds: float | None = None
) -> SessionLease:
    admission = _admission_for(engine)
    await admission.acquire_async(wait_seconds)
    return SessionLease(admission)


def _factory_engine(factory: Callable[[], Session]) -> Engine | None:
    return _engine_of(getattr(factory, "kw", {}).get("bind"))


async def acquire_for_factory_async(
    factory: Callable[[], Session], wait_seconds: float | None = None
) -> SessionLease | None:
    """Loop-side acquire for a background section; ``None`` when the factory has no engine."""
    engine = _factory_engine(factory)
    if engine is None:
        return None
    return await acquire_session_lease_async(engine, wait_seconds)


def run_with_lease(
    lease: SessionLease | None, fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Run ``fn`` in a worker thread with ``lease`` pre-acquired for its ``leased_session``.

    The lease is released when ``fn`` returns or raises (a no-op if already released).
    """
    token = _PRE_ACQUIRED.set(lease)
    try:
        return fn(*args, **kwargs)
    finally:
        _PRE_ACQUIRED.reset(token)
        if lease is not None:
            lease.release()


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
    engine = _factory_engine(factory)
    if engine is None:
        with factory() as session:
            yield session
        return
    lease = _PRE_ACQUIRED.get()
    if lease is not None:
        _PRE_ACQUIRED.set(None)
    else:
        lease = acquire_session_lease(engine, RUNNER_WAIT_SECONDS)
    session = factory()
    attach_lease(session, lease)
    try:
        yield session
    finally:
        release_session(session)
