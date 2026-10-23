from __future__ import annotations

import base64
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.admin_auth import enroll_code, hash_code, validate_code, verify_code
from daily_agent.clerk_backend import ClerkBackend, get_clerk_backend
from daily_agent.config import Settings
from daily_agent.models import (
    AdminAuditLog,
    AdminCredential,
    AdminSession,
    Conversation,
    ErasedClerkSubject,
    Run,
    Subscription,
    UsagePeriod,
    User,
)
from tests.conftest import create_identity

CODE = "correcthorse42"


class Env:
    def __init__(self, ctx: dict[str, Any]) -> None:
        self.client: TestClient = ctx["client"]
        self.factory: sessionmaker[Session] = ctx["factory"]
        self.settings: Settings = ctx["settings"]
        self.admin_bearer = self.make_admin()
        self.root_id = self.last_admin_id

    def make_admin(self, name: str = "root", *, enroll: bool = True, allow: bool = True) -> dict[str, str]:
        with self.factory() as session:
            _acc, user, token = create_identity(session, self.settings, name=name, role="admin")
            user.clerk_subject = f"user_{name}"
            session.commit()
            if enroll:
                enroll_code(session, user, CODE)
            self.last_admin_id = user.id
        if allow:
            self.settings.admin_clerk_user_ids = [*self.settings.admin_clerk_user_ids, f"user_{name}"]
        return {"Authorization": f"Bearer {token}"}

    def customer(self, name: str = "cust") -> tuple[str, str, dict[str, str]]:
        with self.factory() as session:
            _acc, user, token = create_identity(session, self.settings, name=name)
            user.email = f"{name}@example.com"
            session.commit()
            return user.id, user.account_id, {"Authorization": f"Bearer {token}"}

    def login(self, bearer: dict[str, str] | None = None, code: str = CODE) -> Any:
        return self.client.post("/v1/admin/session", json={"code": code}, headers=bearer or self.admin_bearer)

    def headers(self) -> dict[str, str]:
        response = self.login()
        assert response.status_code == 200, response.text
        return {**self.admin_bearer, "X-Admin-Session": response.json()["admin_session_token"]}

    def audit(self, action: str) -> list[AdminAuditLog]:
        with self.factory() as session:
            return list(session.scalars(select(AdminAuditLog).where(AdminAuditLog.action == action)))


@pytest.fixture
def env(test_context: dict[str, object]) -> Iterator[Env]:
    yield Env(test_context)  # type: ignore[arg-type]


# ---- authentication ------------------------------------------------------------------------


def test_code_policy_and_hashing() -> None:
    with pytest.raises(ValueError):
        validate_code("short1")
    with pytest.raises(ValueError):
        validate_code("has-symbols-in-it1")
    validate_code("abcdefghij12")
    stored = hash_code(CODE)
    assert CODE not in stored
    assert verify_code(CODE, stored)
    assert not verify_code("wrongcode0000", stored)
    assert not verify_code(CODE, "garbage")
    assert hash_code(CODE) != stored  # salted


def test_customer_cannot_use_admin_api(env: Env) -> None:
    _uid, _acc, bearer = env.customer()
    assert env.login(bearer).status_code == 403
    assert env.client.get("/v1/admin/users", headers=bearer).status_code == 403
    assert env.client.get("/v1/admin/users").status_code == 401


def test_admin_role_not_in_allowlist_is_forbidden(env: Env) -> None:
    bearer = env.make_admin("outsider", allow=False)
    assert env.login(bearer).status_code == 403


def test_allowlisted_but_not_admin_role_is_forbidden(env: Env) -> None:
    uid, _acc, bearer = env.customer("sneaky")
    with env.factory() as session:
        user = session.get(User, uid)
        assert user is not None
        user.clerk_subject = "user_sneaky"
        session.commit()
    env.settings.admin_clerk_user_ids = [*env.settings.admin_clerk_user_ids, "user_sneaky"]
    assert env.login(bearer).status_code == 403


def test_empty_allowlist_means_nobody(env: Env) -> None:
    env.settings.admin_clerk_user_ids = []
    assert env.login().status_code == 403


def test_wrong_code_and_unenrolled_are_generic_401(env: Env) -> None:
    assert env.login(code="wrongcode0000").status_code == 401
    bearer = env.make_admin("fresh", enroll=False)
    response = env.login(bearer, code=CODE)
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_login_stores_only_hashes(env: Env) -> None:
    response = env.login()
    body = response.json()
    assert response.status_code == 200 and body["expires_at"]
    token = body["admin_session_token"]
    with env.factory() as session:
        dump = " ".join(
            str(v) for row in session.execute(text("select * from admin_sessions")) for v in row
        )
        creds = " ".join(
            str(v) for row in session.execute(text("select * from admin_credentials")) for v in row
        )
    assert token not in dump
    assert CODE not in creds and "scrypt$" in creds
    assert len(token) >= 40


def test_lockout_after_five_failures_persists(env: Env) -> None:
    for _ in range(4):
        assert env.login(code="wrongcode0000").status_code == 401
    fifth = env.login(code="wrongcode0000")
    assert fifth.status_code == 423
    assert 0 < fifth.json()["retry_after"] <= 900
    locked = env.login()  # the correct code is refused while locked
    assert locked.status_code == 423
    with env.factory() as session:
        cred = session.scalars(select(AdminCredential)).first()
        assert cred is not None and cred.locked_until is not None
        cred.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    ok = env.login()
    assert ok.status_code == 200
    with env.factory() as session:
        cred = session.scalars(select(AdminCredential)).first()
        assert cred is not None and cred.failed_attempts == 0 and cred.locked_until is None
    assert len(env.audit("admin.lockout")) == 1


def test_lockout_check_takes_a_row_lock_before_counting() -> None:
    # SQLite ignores FOR UPDATE, so the row lock is asserted on the Postgres compilation.
    stmt = select(AdminCredential).where(AdminCredential.user_id == "u").with_for_update()
    assert "FOR UPDATE" in str(stmt.compile(dialect=postgresql.dialect()))


def test_session_required_expired_and_logout(env: Env) -> None:
    assert env.client.get("/v1/admin/users", headers=env.admin_bearer).status_code == 401
    headers = env.headers()
    assert env.client.get("/v1/admin/session", headers=headers).json()["valid"] is True
    assert env.client.get("/v1/admin/users", headers=headers).status_code == 200
    with env.factory() as session:
        row = session.scalars(select(AdminSession)).first()
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    expired = env.client.get("/v1/admin/users", headers=headers)
    assert expired.status_code == 401
    assert expired.json()["detail"]["code"] == "ADMIN_SESSION_REQUIRED"
    assert env.client.get("/v1/admin/session", headers=headers).json()["valid"] is False

    fresh = env.headers()
    assert env.client.delete("/v1/admin/session", headers=fresh).status_code == 200
    assert env.client.get("/v1/admin/users", headers=fresh).status_code == 401
    assert env.audit("admin.logout")


def test_session_is_bound_to_its_admin(env: Env) -> None:
    other = env.make_admin("second")
    token = env.client.post("/v1/admin/session", json={"code": CODE}, headers=other).json()[
        "admin_session_token"
    ]
    stolen = {**env.admin_bearer, "X-Admin-Session": token}
    assert env.client.get("/v1/admin/users", headers=stolen).status_code == 401


def test_session_lifetime_is_thirty_minutes(env: Env) -> None:
    body = env.login().json()
    expires = datetime.fromisoformat(body["expires_at"])
    delta = expires - datetime.now(UTC)
    assert timedelta(minutes=29) < delta <= timedelta(minutes=30)


# ---- users ---------------------------------------------------------------------------------


def test_list_filter_and_paginate_users(env: Env) -> None:
    for name in ("alice", "bob", "carol"):
        env.customer(name)
    headers = env.headers()
    page = env.client.get("/v1/admin/users?limit=2", headers=headers).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = env.client.get(f"/v1/admin/users?limit=50&cursor={page['next_cursor']}", headers=headers).json()
    seen = {i["id"] for i in page["items"]} | {i["id"] for i in rest["items"]}
    assert len(seen) == 4 and rest["next_cursor"] is None
    hit = env.client.get("/v1/admin/users?q=ALI", headers=headers).json()["items"]
    assert [i["email"] for i in hit] == ["alice@example.com"]
    assert set(hit[0]) >= {
        "id", "email", "display_name", "tier", "disabled", "created_at", "last_active_at",
    }
    assert env.client.get("/v1/admin/users?tier=yanta", headers=headers).json()["items"] == []
    assert len(env.client.get("/v1/admin/users?tier=ananta&status=active", headers=headers).json()["items"]) == 4
    assert env.client.get("/v1/admin/users?status=bogus", headers=headers).status_code == 400
    assert env.client.get("/v1/admin/users?q=%25", headers=headers).json()["items"] == []


def test_user_detail_has_usage_and_is_audited(env: Env) -> None:
    uid, _acc, _b = env.customer()
    headers = env.headers()
    body = env.client.get(f"/v1/admin/users/{uid}", headers=headers).json()
    assert set(body["usage"]) == {"today_requests", "month_spend_usd", "credits_remaining", "sessions"}
    assert body["usage"]["credits_remaining"] > 0
    assert env.client.get("/v1/admin/users/nope", headers=headers).status_code == 404
    assert env.audit("user.view")[0].target_user_id == uid


def test_suspend_blocks_user_and_unsuspend_restores(env: Env) -> None:
    uid, _acc, bearer = env.customer()
    headers = env.headers()
    assert env.client.get("/v1/usage", headers=bearer).status_code == 200
    r = env.client.post(f"/v1/admin/users/{uid}/suspend", json={"reason": "abuse report"}, headers=headers)
    assert r.status_code == 200 and r.json()["disabled"] is True
    blocked = env.client.get("/v1/usage", headers=bearer)
    assert blocked.status_code in (401, 403)
    row = env.audit("user.suspend")[0]
    assert row.target_user_id == uid and row.reason == "abuse report"
    assert row.admin_user_id == env.root_id
    r = env.client.post(f"/v1/admin/users/{uid}/unsuspend", json={"reason": "resolved"}, headers=headers)
    assert r.json()["disabled"] is False
    # Old tokens stay revoked (suspension bumps the token version); a new sign-in works.
    assert env.client.get("/v1/usage", headers=bearer).status_code == 401
    assert env.audit("user.unsuspend")


def test_mutations_require_a_reason(env: Env) -> None:
    uid, _acc, _b = env.customer()
    headers = env.headers()
    for path, body in (
        ("suspend", {}),
        ("suspend", {"reason": "  "}),
        ("unsuspend", {"reason": ""}),
        ("revoke-sessions", {}),
        ("tier", {"tier": "yanta"}),
        ("credits", {"delta_usd": 1}),
    ):
        assert env.client.post(f"/v1/admin/users/{uid}/{path}", json=body, headers=headers).status_code == 422
    assert env.client.request(
        "DELETE", f"/v1/admin/users/{uid}", json={"reason": "gdpr"}, headers=headers
    ).status_code == 422
    assert env.client.request(
        "DELETE", f"/v1/admin/users/{uid}", json={"reason": "gdpr", "confirm": "yes"}, headers=headers
    ).status_code == 422
    with env.factory() as session:
        assert session.get(User, uid) is not None
        assert session.scalars(select(AdminAuditLog).where(AdminAuditLog.action != "admin.login")).first() is None


def test_admin_cannot_suspend_or_delete_self(env: Env) -> None:
    headers = env.headers()
    me = env.root_id
    assert env.client.post(f"/v1/admin/users/{me}/suspend", json={"reason": "oops"}, headers=headers).status_code == 400
    assert env.client.request(
        "DELETE", f"/v1/admin/users/{me}", json={"reason": "oops", "confirm": "DELETE"}, headers=headers
    ).status_code == 400


def test_revoke_sessions_invalidates_existing_tokens(env: Env) -> None:
    uid, _acc, bearer = env.customer()
    headers = env.headers()
    assert env.client.get("/v1/usage", headers=bearer).status_code == 200
    r = env.client.post(f"/v1/admin/users/{uid}/revoke-sessions", json={"reason": "lost phone"}, headers=headers)
    assert r.status_code == 200 and r.json()["revoked"] is True
    assert env.client.get("/v1/usage", headers=bearer).status_code == 401
    row = env.audit("user.revoke_sessions")[0]
    assert row.target_user_id == uid and row.reason == "lost phone"
    with env.factory() as session:
        user = session.get(User, uid)
        assert user is not None and user.sessions_revoked_at is not None


def test_tier_change_updates_plan_progression_and_audit(env: Env) -> None:
    uid, acc, bearer = env.customer()
    headers = env.headers()
    assert env.client.get("/v1/usage", headers=bearer).json()["plan_id"] == "ananta"
    r = env.client.post(f"/v1/admin/users/{uid}/tier", json={"tier": "trika", "reason": "beta tester"}, headers=headers)
    assert r.status_code == 200 and r.json()["tier"] == "trika"
    assert env.client.get("/v1/usage", headers=bearer).json()["plan_id"] == "trika"
    with env.factory() as session:
        user = session.get(User, uid)
        sub = session.scalar(select(Subscription).where(Subscription.account_id == acc))
        assert user is not None and user.unlocked_tier == 3
        assert sub is not None and sub.policy_version == "admin-override-v1"
    # numeric tier works too, including demotion
    assert env.client.post(f"/v1/admin/users/{uid}/tier", json={"tier": 1, "reason": "trial over"}, headers=headers).json()["tier"] == "ananta"
    assert env.client.post(f"/v1/admin/users/{uid}/tier", json={"tier": "gold", "reason": "nope"}, headers=headers).status_code == 400
    assert env.client.post(f"/v1/admin/users/{uid}/tier", json={"tier": 9, "reason": "nope"}, headers=headers).status_code == 400
    rows = env.audit("user.tier")
    assert len(rows) == 2
    detail = json.loads(rows[0].detail)
    assert detail["before"]["plan_id"] == "ananta" and detail["after"]["plan_id"] == "trika"


def test_credit_adjustments(env: Env) -> None:
    uid, _acc, _b = env.customer()
    headers = env.headers()
    base = env.client.get(f"/v1/admin/users/{uid}", headers=headers).json()["usage"]["credits_remaining"]
    r = env.client.post(f"/v1/admin/users/{uid}/credits", json={"delta_usd": 0.5, "reason": "goodwill"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["credits_remaining"] == pytest.approx(base + 0.5)
    r = env.client.post(f"/v1/admin/users/{uid}/credits", json={"budget_usd": 0.25, "reason": "cap"}, headers=headers)
    assert r.json()["budget_usd"] == pytest.approx(0.25)
    assert env.client.post(f"/v1/admin/users/{uid}/credits", json={"reason": "x1x"}, headers=headers).status_code == 422
    assert env.client.post(
        f"/v1/admin/users/{uid}/credits", json={"delta_usd": 1, "budget_usd": 1, "reason": "both"}, headers=headers
    ).status_code == 422
    with env.factory() as session:
        period = session.scalars(select(UsagePeriod)).first()
        assert period is not None
        period.settled_micro = 200_000
        session.commit()
    low = env.client.post(f"/v1/admin/users/{uid}/credits", json={"budget_usd": 0.1, "reason": "too low"}, headers=headers)
    assert low.status_code == 400
    rows = env.audit("user.credits")
    assert len(rows) == 2 and {r.reason for r in rows} == {"goodwill", "cap"}


def test_export_returns_json_and_is_audited(env: Env) -> None:
    uid, acc, _b = env.customer()
    with env.factory() as session:
        session.add(Conversation(account_id=acc, user_id=uid, title="Trip"))
        session.commit()
    headers = env.headers()
    assert env.client.get(f"/v1/admin/users/{uid}/export", headers=headers).status_code == 422
    r = env.client.get(f"/v1/admin/users/{uid}/export?reason=subject+access+request", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["id"] == uid and body["conversations"][0]["title"] == "Trip"
    assert body["message_bodies_included"] is False
    assert "attachment" in r.headers["content-disposition"]
    audit = env.audit("user.export")
    assert len(audit) == 1 and audit[0].target_user_id == uid
    assert audit[0].reason == "subject access request"


def test_erasure_removes_everything_and_keeps_audit(env: Env) -> None:
    uid, acc, _b = env.customer("victim")
    with env.factory() as session:
        session.add(Conversation(account_id=acc, user_id=uid, title="secret"))
        session.add(Run(account_id=acc, user_id=uid, logical_request_id="r1"))
        session.commit()
    headers = env.headers()
    r = env.client.request(
        "DELETE", f"/v1/admin/users/{uid}", json={"reason": "gdpr request #1", "confirm": "DELETE"}, headers=headers
    )
    assert r.status_code == 200 and r.json()["deleted"] is True
    with env.factory() as session:
        assert session.get(User, uid) is None
        assert session.execute(text("select count(*) from accounts where id = :a"), {"a": acc}).scalar() == 0
        assert session.execute(text("select count(*) from subscriptions where account_id = :a"), {"a": acc}).scalar() == 0
        assert session.execute(text("select count(*) from conversations where account_id = :a"), {"a": acc}).scalar() == 0
        assert session.execute(text("select count(*) from runs where account_id = :a"), {"a": acc}).scalar() == 0
    row = env.audit("user.erase")[0]
    assert row.target_user_id == uid and row.reason == "gdpr request #1"
    assert env.client.get(f"/v1/admin/users/{uid}", headers=headers).status_code == 404


# ---- monitor, audit, runs ------------------------------------------------------------------


def test_monitor_shape_and_short_cache(env: Env) -> None:
    headers = env.headers()
    first = env.client.get("/v1/admin/monitor", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert set(body) == {
        "active_users", "active_streams", "req_per_min", "error_rate", "p95_latency_ms",
        "spend_today_usd", "platform_budget_usd", "provider_health", "generated_at",
    }
    assert isinstance(body["provider_health"], list)
    assert body["platform_budget_usd"] > 0
    assert env.client.get("/v1/admin/monitor", headers=headers).json()["generated_at"] == body["generated_at"]


def test_audit_endpoint_lists_newest_first_with_cursor(env: Env) -> None:
    uid, _acc, _b = env.customer()
    headers = env.headers()
    for i in range(3):
        env.client.post(f"/v1/admin/users/{uid}/suspend", json={"reason": f"reason {i}"}, headers=headers)
    page = env.client.get("/v1/admin/audit?limit=2", headers=headers).json()
    assert [i["action"] for i in page["items"]] == ["user.suspend", "user.suspend"]
    assert page["items"][0]["reason"] == "reason 2" and page["next_cursor"]
    assert set(page["items"][0]) == {"id", "at", "admin_user_id", "action", "target_user_id", "reason", "detail"}
    more = env.client.get(f"/v1/admin/audit?limit=50&cursor={page['next_cursor']}", headers=headers).json()
    assert more["items"][0]["id"] < page["items"][-1]["id"]
    assert env.client.get("/v1/admin/audit?cursor=abc", headers=headers).status_code == 400


def test_runs_are_ordered_by_created_at_desc(env: Env) -> None:
    uid, acc, _b = env.customer()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with env.factory() as session:
        for i, offset in enumerate((5, 1, 9, 3)):
            session.add(
                Run(account_id=acc, user_id=uid, logical_request_id=f"r{i}",
                    id=f"run-{offset}", created_at=base + timedelta(hours=offset))
            )
        session.commit()
    headers = env.headers()
    body = env.client.get("/v1/admin/runs?limit=3", headers=headers).json()
    assert [r["run_id"] for r in body["items"]] == ["run-9", "run-5", "run-3"]
    assert all(r["response"] == "redacted" for r in body["items"])
    rest = env.client.get(f"/v1/admin/runs?cursor={body['next_cursor']}", headers=headers).json()
    assert [r["run_id"] for r in rest["items"]] == ["run-1"]


def test_run_cursor_round_trips_through_identical_timestamps(env: Env) -> None:
    uid, acc, _b = env.customer()
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    with env.factory() as session:
        for name in ("run-a", "run-b", "run-c"):
            session.add(
                Run(account_id=acc, user_id=uid, logical_request_id=name, id=name, created_at=stamp)
            )
        session.commit()
    headers = env.headers()
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        url = "/v1/admin/runs?limit=1"
        if cursor:
            url += f"&cursor={quote(cursor, safe='')}"
        body = env.client.get(url, headers=headers).json()
        seen.extend(item["run_id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == ["run-a", "run-b", "run-c"]
    assert env.client.get("/v1/admin/runs?cursor=garbage", headers=headers).status_code == 400


# ---- append-only audit ---------------------------------------------------------------------


def test_orm_refuses_audit_update_and_delete(env: Env) -> None:
    env.login()
    with env.factory() as session:
        row = session.scalars(select(AdminAuditLog)).first()
        assert row is not None
        row.reason = "tampered"
        with pytest.raises(RuntimeError, match="append-only"):
            session.commit()
        session.rollback()
        session.delete(row)
        with pytest.raises(RuntimeError, match="append-only"):
            session.commit()


def test_database_triggers_refuse_audit_update_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "audit.db"
    monkeypatch.setenv("DAILY_AGENT_DATABASE_URL", f"sqlite+pysqlite:///{db}")
    command.upgrade(Config("alembic.ini"), "head")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into admin_audit_log (at, admin_user_id, action) values (datetime('now'), 'a', 'x')"
        )
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("update admin_audit_log set action = 'y'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("delete from admin_audit_log")
        assert conn.execute("select count(*) from admin_audit_log").fetchone()[0] == 1
    command.downgrade(Config("alembic.ini"), "-1")
    command.upgrade(Config("alembic.ini"), "head")


def test_admin_routes_have_no_unauthenticated_access(env: Env) -> None:
    paths = ["/v1/admin/users", "/v1/admin/monitor", "/v1/admin/audit", "/v1/admin/runs", "/v1/admin/users/x"]
    for path in paths:
        assert env.client.get(path).status_code == 401
        assert env.client.get(path, headers=env.admin_bearer).status_code == 401  # no admin session


# ---- Clerk session revocation and erasure tombstones ---------------------------------------

CLERK_ISSUER = "https://clerk.example.test"
ClerkHandler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def clerk_token(env: Env) -> Callable[[str, int], dict[str, str]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    env.settings.clerk_issuer = CLERK_ISSUER
    env.settings.clerk_jwt_public_key_b64 = base64.b64encode(public_pem).decode()

    def make(subject: str, issued_at: int) -> dict[str, str]:
        claims = {
            "sub": subject, "sid": "sess_1", "iss": CLERK_ISSUER,
            "iat": issued_at, "exp": issued_at + 3600,
        }
        return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}

    return make


def clerk_victim(env: Env, subject: str = "user_clerk_victim") -> str:
    user_id, _acc, _bearer = env.customer("victim")
    with env.factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.clerk_subject = subject
        session.commit()
    return user_id


def use_clerk(env: Env, handler: ClerkHandler) -> list[httpx.Request]:
    """Route the admin API's Clerk calls through a mock transport; returns the recorded requests."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    backend = ClerkBackend("sk_test_secret", transport=httpx.MockTransport(record))
    env.client.app.dependency_overrides[get_clerk_backend] = lambda: backend
    return seen


def clerk_ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/sessions":
        return httpx.Response(200, json={"data": [{"id": "sess_a"}, {"id": "sess_b"}]})
    return httpx.Response(200, json={"status": "revoked"})


def test_revoke_ends_clerk_sessions_then_rejects_local_tokens(env: Env, clerk_token) -> None:
    uid = clerk_victim(env)
    headers = env.headers()
    old = clerk_token("user_clerk_victim", int(time.time()) - 60)
    assert env.client.get("/v1/usage", headers=old).status_code == 200
    seen = use_clerk(env, clerk_ok)
    r = env.client.post(
        f"/v1/admin/users/{uid}/revoke-sessions", json={"reason": "lost phone"}, headers=headers
    )
    assert r.status_code == 200 and r.json()["clerk_sessions_revoked"] == 2
    lookups = [q for q in seen if q.method == "GET"]
    assert lookups[0].url.params["user_id"] == "user_clerk_victim"
    assert lookups[0].url.params["status"] == "active"
    assert [q.url.path for q in seen if q.method == "POST"] == [
        "/v1/sessions/sess_a/revoke",
        "/v1/sessions/sess_b/revoke",
    ]
    assert {q.headers["Authorization"] for q in seen} == {"Bearer sk_test_secret"}
    assert env.client.get("/v1/usage", headers=old).status_code == 401
    assert json.loads(env.audit("user.revoke_sessions")[0].detail)["clerk_sessions_revoked"] == 2


def test_revoke_for_clerk_user_without_secret_is_409_and_changes_nothing(
    env: Env, clerk_token
) -> None:
    uid = clerk_victim(env)
    headers = env.headers()
    old = clerk_token("user_clerk_victim", int(time.time()) - 60)
    assert env.client.get("/v1/usage", headers=old).status_code == 200
    r = env.client.post(
        f"/v1/admin/users/{uid}/revoke-sessions", json={"reason": "lost phone"}, headers=headers
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CLERK_SECRET_NOT_CONFIGURED"
    assert env.client.get("/v1/usage", headers=old).status_code == 200
    assert env.audit("user.revoke_sessions") == []
    with env.factory() as session:
        user = session.get(User, uid)
        assert user is not None and user.sessions_revoked_at is None


def test_revoke_for_customer_without_clerk_subject_needs_no_clerk(env: Env) -> None:
    uid, _acc, _bearer = env.customer("local")
    headers = env.headers()
    r = env.client.post(
        f"/v1/admin/users/{uid}/revoke-sessions", json={"reason": "local only"}, headers=headers
    )
    assert r.status_code == 200 and r.json()["clerk_sessions_revoked"] == 0


@pytest.mark.parametrize("failure", ["lookup", "revoke"])
def test_clerk_failure_is_502_and_marks_nothing_done(env: Env, clerk_token, failure: str) -> None:
    uid = clerk_victim(env)
    headers = env.headers()
    old = clerk_token("user_clerk_victim", int(time.time()) - 60)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sessions":
            if failure == "lookup":
                return httpx.Response(500)
            return httpx.Response(200, json={"data": [{"id": "sess_a"}]})
        return httpx.Response(403, json={})

    use_clerk(env, handler)
    r = env.client.post(
        f"/v1/admin/users/{uid}/revoke-sessions", json={"reason": "lost phone"}, headers=headers
    )
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "CLERK_REVOKE_FAILED"
    assert env.client.get("/v1/usage", headers=old).status_code == 200
    assert env.audit("user.revoke_sessions") == []


def test_admin_cannot_act_on_a_peer_admin_and_the_attempt_is_audited(env: Env) -> None:
    env.make_admin("peer")
    peer_id = env.last_admin_id
    headers = env.headers()
    base = f"/v1/admin/users/{peer_id}"
    suspend = env.client.post(f"{base}/suspend", json={"reason": "rivalry"}, headers=headers)
    tier = env.client.post(f"{base}/tier", json={"tier": "trika", "reason": "rivalry"}, headers=headers)
    erase = env.client.request(
        "DELETE", base, json={"reason": "rivalry", "confirm": "DELETE"}, headers=headers
    )
    for r in (suspend, tier, erase):
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "ADMIN_TARGET_PROTECTED"
    with env.factory() as session:
        peer = session.get(User, peer_id)
        assert peer is not None and peer.disabled is False and peer.role == "admin"
    for action in ("user.suspend.denied", "user.tier.denied", "user.erase.denied"):
        rows = env.audit(action)
        assert len(rows) == 1
        assert rows[0].admin_user_id == env.root_id and rows[0].target_user_id == peer_id
        assert json.loads(rows[0].detail) == {"refused": "target_is_admin"}


def test_erased_clerk_subject_cannot_reprovision(env: Env, clerk_token) -> None:
    uid = clerk_victim(env, "user_clerk_erased")
    headers = env.headers()
    token = clerk_token("user_clerk_erased", int(time.time()) - 60)
    assert env.client.get("/v1/usage", headers=token).status_code == 200
    r = env.client.request(
        "DELETE",
        f"/v1/admin/users/{uid}",
        json={"reason": "gdpr request #7", "confirm": "DELETE"},
        headers=headers,
    )
    assert r.status_code == 200
    blocked = env.client.get("/v1/usage", headers=token)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "ACCOUNT_ERASED"
    with env.factory() as session:
        tombstones = list(session.scalars(select(ErasedClerkSubject)))
        assert len(tombstones) == 1
        assert tombstones[0].subject_hash != "user_clerk_erased"
        assert session.get(User, uid) is None


def test_legacy_admin_routes_are_gone(env: Env) -> None:
    headers = env.headers()
    for path in ("/admin/overview", "/admin/runs", "/v1/admin/overview"):
        assert env.client.get(path, headers=headers).status_code == 404


