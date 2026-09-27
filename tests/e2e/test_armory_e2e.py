from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from daily_agent.models import User
from daily_agent.security import issue_development_token
from tests.conftest import create_identity

pytestmark = pytest.mark.e2e


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign(raw: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_armory_requires_auth(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    assert client.get("/v1/armory").status_code == 401  # type: ignore[union-attr]
    assert client.put("/v1/armory/active-theme", json={"active_theme": 1}).status_code == 401  # type: ignore[union-attr]


def test_armory_defaults_and_tier_structure(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="DefaultUser")  # type: ignore[arg-type]

    response = client.get("/v1/armory", headers=auth(token))  # type: ignore[union-attr]
    assert response.status_code == 200
    data = response.json()
    assert data["unlocked_tier"] == 1
    assert data["active_theme"] == 1
    tiers = data["tiers"]
    assert len(tiers) == 4
    assert [t["id"] for t in tiers] == [1, 2, 3, 4]
    assert tiers[0] == {"id": 1, "key": "ananta", "label": "Ananta", "plan_id": "ananta"}
    assert tiers[1] == {"id": 2, "key": "yanta", "label": "Yanta", "plan_id": "yanta"}
    assert tiers[2] == {"id": 3, "key": "trika", "label": "Trika", "plan_id": "trika"}
    assert tiers[3] == {"id": 4, "key": "parth", "label": "Parth", "plan_id": "parth"}


def test_activating_locked_tier_returns_403_and_leaves_state_unchanged(
    test_context: dict[str, object]
) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="LockedUser")  # type: ignore[arg-type]

    res = client.put("/v1/armory/active-theme", headers=auth(token), json={"active_theme": 2})  # type: ignore[union-attr]
    assert res.status_code == 403
    assert res.json() == {"detail": {"code": "TIER_LOCKED", "unlocked_tier": 1}}

    # State unchanged
    get_res = client.get("/v1/armory", headers=auth(token))  # type: ignore[union-attr]
    assert get_res.status_code == 200
    assert get_res.json()["unlocked_tier"] == 1
    assert get_res.json()["active_theme"] == 1


def test_invalid_active_theme_values_return_422(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="ValidationUser")  # type: ignore[arg-type]

    invalid_bodies = [
        {"active_theme": 0},
        {"active_theme": 5},
        {"active_theme": "2"},
        {"active_theme": True},
        {"active_theme": None},
        {},
    ]
    for body in invalid_bodies:
        res = client.put("/v1/armory/active-theme", headers=auth(token), json=body)  # type: ignore[union-attr]
        assert res.status_code == 422, f"Expected 422 for body {body}, got {res.status_code}"


def test_billing_lifecycle_upgrade_downgrade_and_cancel(
    test_context: dict[str, object]
) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, token = create_identity(session, settings, name="LifecycleUser")  # type: ignore[arg-type]

    def post_billing_event(event_id: str, version: int, plan: str, event_type: str = "activated") -> None:
        raw = json.dumps(
            {
                "event_id": event_id,
                "account_id": account.id,
                "version": version,
                "type": event_type,
                "plan_id": plan,
            },
            separators=(",", ":"),
        ).encode()
        res = client.post(  # type: ignore[union-attr]
            "/webhooks/billing-sandbox",
            content=raw,
            headers={"X-Signature-SHA256": sign(raw, settings.webhook_secret), "Content-Type": "application/json"},  # type: ignore[union-attr]
        )
        assert res.status_code == 200

    # 1. Upgrade to part (tier 4)
    post_billing_event("evt-1", 1, "parth")
    get_res = client.get("/v1/armory", headers=auth(token))  # type: ignore[union-attr]
    assert get_res.status_code == 200
    assert get_res.json()["unlocked_tier"] == 4
    assert get_res.json()["active_theme"] == 1

    # 2. Activate theme 4
    put_res = client.put("/v1/armory/active-theme", headers=auth(token), json={"active_theme": 4})  # type: ignore[union-attr]
    assert put_res.status_code == 200
    assert put_res.json()["unlocked_tier"] == 4
    assert put_res.json()["active_theme"] == 4

    # 3. Downgrade to yanta (tier 2) -> GET returns (2, 2)
    post_billing_event("evt-2", 2, "yanta")
    get_res2 = client.get("/v1/armory", headers=auth(token))  # type: ignore[union-attr]
    assert get_res2.status_code == 200
    assert get_res2.json()["unlocked_tier"] == 2
    assert get_res2.json()["active_theme"] == 2

    # 4. Cancelled subscription -> (1, 1)
    post_billing_event("evt-3", 3, "yanta", event_type="cancelled")
    get_res3 = client.get("/v1/armory", headers=auth(token))  # type: ignore[union-attr]
    assert get_res3.status_code == 200
    assert get_res3.json()["unlocked_tier"] == 1
    assert get_res3.json()["active_theme"] == 1


def test_multi_user_account_independent_themes_and_isolation(
    test_context: dict[str, object]
) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account_a, _user_a1, token_a1 = create_identity(session, settings, name="A1")  # type: ignore[arg-type]
        user_a2 = User(account_id=account_a.id, display_name="A2", role="customer")
        session.add(user_a2)
        session.commit()
        token_a2 = issue_development_token(user_a2, settings)  # type: ignore[arg-type]

        _account_b, _user_b, token_b = create_identity(session, settings, name="B")  # type: ignore[arg-type]

    # Upgrade Account A to part (tier 4)
    raw = json.dumps(
        {
            "event_id": "evt-a-parth",
            "account_id": account_a.id,
            "version": 1,
            "type": "activated",
            "plan_id": "parth",
        },
        separators=(",", ":"),
    ).encode()
    client.post(  # type: ignore[union-attr]
        "/webhooks/billing-sandbox",
        content=raw,
        headers={"X-Signature-SHA256": sign(raw, settings.webhook_secret), "Content-Type": "application/json"},  # type: ignore[union-attr]
    )

    # User A1 sets active_theme = 4
    res_a1 = client.put("/v1/armory/active-theme", headers=auth(token_a1), json={"active_theme": 4})  # type: ignore[union-attr]
    assert res_a1.status_code == 200
    assert res_a1.json()["unlocked_tier"] == 4
    assert res_a1.json()["active_theme"] == 4

    # User A2 sets active_theme = 2
    res_a2 = client.put("/v1/armory/active-theme", headers=auth(token_a2), json={"active_theme": 2})  # type: ignore[union-attr]
    assert res_a2.status_code == 200
    assert res_a2.json()["unlocked_tier"] == 4
    assert res_a2.json()["active_theme"] == 2

    # User A1's theme is still 4
    get_a1 = client.get("/v1/armory", headers=auth(token_a1))  # type: ignore[union-attr]
    assert get_a1.json()["unlocked_tier"] == 4
    assert get_a1.json()["active_theme"] == 4

    # Account B is unaffected (still tier 1)
    get_b = client.get("/v1/armory", headers=auth(token_b))  # type: ignore[union-attr]
    assert get_b.json()["unlocked_tier"] == 1
    assert get_b.json()["active_theme"] == 1

    # Account B cannot activate tier 4
    res_b = client.put("/v1/armory/active-theme", headers=auth(token_b), json={"active_theme": 4})  # type: ignore[union-attr]
    assert res_b.status_code == 403


def test_messages_endpoint_behaves_identically_across_themes(
    test_context: dict[str, object]
) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, _user, token = create_identity(session, settings, name="ThemeAgentUser")  # type: ignore[arg-type]

    # Webhook upgrade to yanta
    raw = json.dumps(
        {
            "event_id": "evt-upgrade-yanta",
            "account_id": account.id,
            "version": 1,
            "type": "activated",
            "plan_id": "yanta",
        },
        separators=(",", ":"),
    ).encode()
    client.post(  # type: ignore[union-attr]
        "/webhooks/billing-sandbox",
        content=raw,
        headers={"X-Signature-SHA256": sign(raw, settings.webhook_secret), "Content-Type": "application/json"},  # type: ignore[union-attr]
    )

    # Message under active_theme 1
    msg1 = client.post(  # type: ignore[union-attr]
        "/v1/messages",
        headers=auth(token),
        json={"text": "Message with theme 1", "idempotency_key": "msg-theme-1"},
    )
    assert msg1.status_code == 200
    assert msg1.json()["outcome"] == "ACCEPT"

    # Switch to theme 2
    put_res = client.put("/v1/armory/active-theme", headers=auth(token), json={"active_theme": 2})  # type: ignore[union-attr]
    assert put_res.status_code == 200
    assert put_res.json()["active_theme"] == 2

    # Message under active_theme 2
    msg2 = client.post(  # type: ignore[union-attr]
        "/v1/messages",
        headers=auth(token),
        json={"text": "Message with theme 2", "idempotency_key": "msg-theme-2"},
    )
    assert msg2.status_code == 200
    assert msg2.json()["outcome"] == "ACCEPT"
