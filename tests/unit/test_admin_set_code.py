from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from daily_agent.admin_auth import enroll_code, verify_code
from daily_agent.config import Settings
from daily_agent.db import create_schema
from daily_agent.models import AdminAuditLog, AdminCredential, Base
from scripts import admin_set_code
from tests.conftest import create_identity

OLD_CODE = "correcthorse42"
SUBJECT = "user_root"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def seeded(engine, monkeypatch):
    settings = Settings(environment="test", admin_clerk_user_ids=[SUBJECT])
    monkeypatch.setattr(admin_set_code, "get_settings", lambda: settings)
    monkeypatch.setattr(admin_set_code, "get_engine", lambda: engine)
    with Session(engine) as session:
        _acc, user, _token = create_identity(session, settings, name="root", role="admin")
        user.clerk_subject = SUBJECT
        session.commit()
        enroll_code(session, user, OLD_CODE)
        credential = session.get(AdminCredential, user.id)
        assert credential is not None
        credential.failed_attempts = 3
        credential.locked_until = datetime.now(UTC) + timedelta(minutes=10)
        session.commit()
        return user.id


def _credential(engine, user_id: str) -> AdminCredential:
    with Session(engine) as session:
        credential = session.get(AdminCredential, user_id)
        assert credential is not None
        session.expunge(credential)
        return credential


def _audit_count(engine, action: str) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action == action)
        ) or 0


def test_set_code_enrolls_code_and_writes_audit_row(engine, seeded) -> None:
    assert admin_set_code.main(["--clerk-subject", SUBJECT, "--generate"]) == 0

    credential = _credential(engine, seeded)
    assert credential.failed_attempts == 0
    assert credential.locked_until is None
    assert not verify_code(OLD_CODE, credential.code_hash)
    assert _audit_count(engine, "admin.code_set") == 1


def test_audit_failure_rolls_back_credential_change(engine, seeded, monkeypatch) -> None:
    before = _credential(engine, seeded)

    def failing_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(admin_set_code, "append_audit", failing_audit)

    with pytest.raises(RuntimeError, match="audit insert failed"):
        admin_set_code.main(["--clerk-subject", SUBJECT, "--generate"])

    after = _credential(engine, seeded)
    assert after.code_hash == before.code_hash
    assert verify_code(OLD_CODE, after.code_hash)
    assert after.failed_attempts == 3
    assert after.locked_until is not None
    assert _audit_count(engine, "admin.code_set") == 0
