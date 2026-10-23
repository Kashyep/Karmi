from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from daily_agent.models import AdminAuditLog, Subscription, User
from tests.unit.test_admin_api import Env


@pytest.fixture
def env(test_context: dict[str, object]):
    yield Env(test_context)  # type: ignore[arg-type]


def customer(env: Env, name: str) -> str:
    return env.customer(name)[0]


def test_new_routes_require_admin_session(env: Env) -> None:
    uid = customer(env, "missing-session")
    for method, path, body in (("patch", f"/v1/admin/users/{uid}", {"display_name": "x", "reason": "r"}), ("post", f"/v1/admin/users/{uid}/tier", {"tier": "yanta", "reason": "r"}), ("post", "/v1/admin/users/bulk-tier", {"user_ids": [uid], "tier": "yanta", "reason": "r"})):
        assert getattr(env.client, method)(path, json=body).status_code in {401, 403}


def test_bulk_duplicates_and_audits(env: Env) -> None:
    uid = customer(env, "bulk-regression")
    headers = env.headers()
    assert env.client.post("/v1/admin/users/bulk-tier", headers=headers, json={"user_ids": [uid, uid], "tier": "yanta", "reason": "r"}).status_code == 422
    assert env.client.post("/v1/admin/users/bulk-tier", headers=headers, json={"user_ids": [uid], "tier": "yanta", "reason": "run"}).status_code == 200
    with env.factory() as session:
        assert len(list(session.scalars(select(AdminAuditLog).where(AdminAuditLog.action == "user.tier")))) == 1


def test_clearing_label_and_invalid_tiers(env: Env) -> None:
    uid = customer(env, "clear-label")
    headers = env.headers()
    assert env.client.patch(f"/v1/admin/users/{uid}", headers=headers, json={"tester_label": "", "reason": "clear"}).status_code == 200
    assert env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": "²", "reason": "bad"}).status_code == 422
    assert env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": True, "reason": "bad"}).status_code == 422


def test_stacked_grant_preserves_base_revert(env: Env) -> None:
    uid = customer(env, "stacked")
    headers = env.headers()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": "trika", "expires_at": future, "reason": "first"}).status_code == 200
    assert env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": "parth", "expires_at": future, "reason": "second"}).status_code == 200
    with env.factory() as session:
        user = session.get(User, uid)
        assert user is not None
        sub = session.scalar(select(Subscription).where(Subscription.account_id == user.account_id))
        assert sub is not None and sub.revert_plan_id == "ananta"
