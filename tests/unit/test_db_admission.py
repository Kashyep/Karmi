from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from daily_agent import db_admission
from daily_agent.db_admission import (
    DatabaseAdmission,
    DatabaseBusy,
    SessionLease,
    acquire_session_lease,
    attach_lease,
    install_admission,
    leased_session,
    release_session,
)


def test_saturated_admission_raises_database_busy() -> None:
    admission = DatabaseAdmission(capacity=1, wait_seconds=0.01)
    admission.acquire()
    with pytest.raises(DatabaseBusy) as excinfo:
        admission.acquire()
    assert excinfo.value.retry_after_s >= 1


def test_lease_release_is_idempotent_and_frees_one_slot() -> None:
    admission = DatabaseAdmission(capacity=1, wait_seconds=0.01)
    admission.acquire()
    lease = SessionLease(admission)
    lease.release()
    lease.release()
    # Exactly one slot was returned: it is available once more, and no more than one.
    admission.acquire()
    with pytest.raises(DatabaseBusy):
        admission.acquire()


def test_release_session_closes_and_frees_lease() -> None:
    engine = create_engine("sqlite:///:memory:")
    install_admission(engine, capacity=1, wait_seconds=0.01)
    factory = sessionmaker(bind=engine)

    lease = acquire_session_lease(engine, 0.01)
    session = factory()
    attach_lease(session, lease)
    assert session.execute(text("select 1")).scalar() == 1

    release_session(session)
    # The slot is free again, so a second lease succeeds immediately.
    second = acquire_session_lease(engine, 0.01)
    second.release()


def test_leased_session_fails_busy_when_engine_saturated(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    install_admission(engine, capacity=1, wait_seconds=0.01)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(db_admission, "RUNNER_WAIT_SECONDS", 0.01)

    held = acquire_session_lease(engine, 0.01)
    try:
        with pytest.raises(DatabaseBusy), leased_session(factory):
            pass
    finally:
        held.release()
