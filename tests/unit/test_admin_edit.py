from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from daily_agent.models import AdminAuditLog, Subscription, User
from tests.unit.test_admin_api import Env


@pytest.fixture
def edit_env(test_context: dict[str, object]):
    yield Env(test_context)  # type: ignore[arg-type]


def customer(edit_env: Env, name: str = "edit-customer") -> str:
    uid, _account, _bearer = edit_env.customer(name)
    return uid


def test_patch_edit_and_audit(edit_env: Env) -> None:
    uid = customer(edit_env)
    response = edit_env.client.patch(
        f"/v1/admin/users/{uid}",
        headers=edit_env.headers(),
        json={"display_name": "Renamed", "tester": True, "tester_label": "qa", "admin_notes": "note", "reason": "support request"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Renamed"
    with edit_env.factory() as session:
        user = session.get(User, uid)
        assert user is not None and user.tester and user.tester_label == "qa"
        audit = session.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "user.edit"))
        assert audit is not None and audit.reason == "support request"


def test_patch_validation(edit_env: Env) -> None:
    uid = customer(edit_env, "validation")
    headers = edit_env.headers()
    assert edit_env.client.patch(f"/v1/admin/users/{uid}", headers=headers, json={"display_name": "", "reason": "why"}).status_code == 422
    assert edit_env.client.patch(f"/v1/admin/users/{uid}", headers=headers, json={"admin_notes": "x" * 2001, "reason": "why"}).status_code == 422
    assert edit_env.client.patch(f"/v1/admin/users/{uid}", headers=headers, json={"display_name": "x"}).status_code == 422


def test_tier_promote_demote_and_expiry(edit_env: Env) -> None:
    uid = customer(edit_env, "tier")
    headers = edit_env.headers()
    promoted = edit_env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": "trika", "reason": "temporary", "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()})
    assert promoted.status_code == 200 and promoted.json()["effective_plan"] == "trika"
    with edit_env.factory() as session:
        sub = session.scalar(select(Subscription).join(User, User.account_id == Subscription.account_id).where(User.id == uid))
        assert sub is not None
        sub.tier_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    detail = edit_env.client.get(f"/v1/admin/users/{uid}", headers=headers)
    assert detail.status_code == 200 and detail.json()["effective_plan"] == "ananta"
    demoted = edit_env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": "yanta", "reason": "restore"})
    assert demoted.status_code == 200 and demoted.json()["effective_plan"] == "yanta"
    assert edit_env.client.post(f"/v1/admin/users/{uid}/tier", headers=headers, json={"tier": "trika", "expires_at": "2000-01-01T00:00:00Z", "reason": "bad"}).status_code == 422


def test_bulk_limits_unknown_and_admin_protection(edit_env: Env) -> None:
    uid = customer(edit_env, "bulk")
    headers = edit_env.headers()
    assert edit_env.client.post("/v1/admin/users/bulk-tier", headers=headers, json={"user_ids": [uid], "tier": "yanta", "reason": "bulk"}).json()["updated"] == 1
    assert edit_env.client.post("/v1/admin/users/bulk-tier", headers=headers, json={"user_ids": [uid] * 101, "tier": "yanta", "reason": "bulk"}).status_code == 422
    assert edit_env.client.post("/v1/admin/users/bulk-tier", headers=headers, json={"user_ids": ["missing"], "tier": "yanta", "reason": "bulk"}).status_code == 404
    assert edit_env.client.post(f"/v1/admin/users/{edit_env.root_id}/tier", headers=headers, json={"tier": "yanta", "reason": "self"}).status_code == 403
    edit_env.make_admin("peer")
    peer_id = edit_env.last_admin_id
    assert edit_env.client.post(f"/v1/admin/users/{peer_id}/tier", headers=headers, json={"tier": "yanta", "reason": "peer"}).status_code == 403
    assert edit_env.client.post("/v1/admin/users/no-user/tier", headers=headers, json={"tier": "yanta", "reason": "missing"}).status_code == 404


def test_list_filters(edit_env: Env) -> None:
    uid = customer(edit_env, "filter")
    headers = edit_env.headers()
    edit_env.client.patch(f"/v1/admin/users/{uid}", headers=headers, json={"tester_label": "special", "reason": "tag"})
    assert any(item["id"] == uid for item in edit_env.client.get("/v1/admin/users?tester_label=special", headers=headers).json()["items"])
    edit_env.client.post(f"/v1/admin/users/{uid}/suspend", headers=headers, json={"reason": "hold"})
    assert any(item["id"] == uid for item in edit_env.client.get("/v1/admin/users?suspended=true", headers=headers).json()["items"])
