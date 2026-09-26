import hashlib
import hmac
import json
import time

from sqlalchemy import select

from daily_agent.config import Settings, get_settings
from daily_agent.models import Subscription, UsageWindow
from tests.conftest import create_identity


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign(raw: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def sign_event(event_id: str, timestamp: str, raw: bytes, secret: str) -> str:
    signable = f"{event_id}.{timestamp}.".encode() + raw
    return hmac.new(secret.encode(), signable, hashlib.sha256).hexdigest()


def test_identity_scopes_private_notes(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account_a, _user_a, token_a = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        _account_b, _user_b, token_b = create_identity(session, settings, name="B")  # type: ignore[arg-type]
    created = client.post("/v1/notes", headers=auth(token_a), json={"content": "A private"})  # type: ignore[union-attr]
    assert created.status_code == 201
    note_id = created.json()["id"]
    assert client.get("/v1/notes", headers=auth(token_b)).json() == []  # type: ignore[union-attr]
    denied = client.delete(f"/v1/notes/{note_id}", headers=auth(token_b))  # type: ignore[union-attr]
    assert denied.status_code == 404
    assert client.get("/v1/notes", headers=auth(token_a)).json()[0]["content"] == "A private"  # type: ignore[union-attr]


def test_message_dedupes_usage_and_persists_outbox(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
    payload = {"text": "Write a concise hello", "idempotency_key": "request-0001"}
    first = client.post("/v1/messages", headers=auth(token), json=payload)  # type: ignore[union-attr]
    second = client.post("/v1/messages", headers=auth(token), json=payload)  # type: ignore[union-attr]
    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    with factory() as session:  # type: ignore[operator]
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert window is not None
        assert window.everyday_used == 1
        assert window.settled_micro == 100


def test_signed_event_is_deduplicated(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    settings = test_context["settings"]
    raw = b'{"message":"synthetic"}'
    ts = str(int(time.time()))
    headers = {
        "X-Event-ID": "evt-0001",
        "X-Timestamp": ts,
        "X-Signature-SHA256": sign_event("evt-0001", ts, raw, settings.webhook_secret),  # type: ignore[union-attr]
        "Content-Type": "application/json",
    }
    bad = client.post("/webhooks/internal-test", content=raw, headers={**headers, "X-Signature-SHA256": "bad"})  # type: ignore[union-attr]
    assert bad.status_code == 401
    stale = client.post(  # type: ignore[union-attr]
        "/webhooks/internal-test",
        content=raw,
        headers={**headers, "X-Timestamp": "1", "X-Signature-SHA256": sign_event("evt-0001", "1", raw, settings.webhook_secret)},
    )
    assert stale.status_code == 401
    # A valid body signature cannot be replayed under a different event id.
    rebadged = client.post(  # type: ignore[union-attr]
        "/webhooks/internal-test",
        content=raw,
        headers={**headers, "X-Event-ID": "evt-0002"},
    )
    assert rebadged.status_code == 401
    first = client.post("/webhooks/internal-test", content=raw, headers=headers)  # type: ignore[union-attr]
    second = client.post("/webhooks/internal-test", content=raw, headers=headers)  # type: ignore[union-attr]
    assert first.json()["accepted"] is True
    assert second.json()["duplicate"] is True


def test_billing_event_is_order_aware_and_idempotent(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]

    def post_event(event_id: str, version: int, plan: str) -> object:
        raw = json.dumps(
            {"event_id": event_id, "account_id": account.id, "version": version, "type": "activated", "plan_id": plan},
            separators=(",", ":"),
        ).encode()
        return client.post(  # type: ignore[union-attr]
            "/webhooks/billing-sandbox",
            content=raw,
            headers={"X-Signature-SHA256": sign(raw, settings.webhook_secret), "Content-Type": "application/json"},  # type: ignore[union-attr]
        )

    newer = post_event("bill-2", 2, "trika")
    stale = post_event("bill-1", 1, "yanta")
    duplicate = post_event("bill-2", 2, "trika")
    assert newer.json()["stale"] is False  # type: ignore[union-attr]
    assert stale.json()["stale"] is True  # type: ignore[union-attr]
    assert duplicate.json()["duplicate"] is True  # type: ignore[union-attr]
    with factory() as session:  # type: ignore[operator]
        subscription = session.scalar(select(Subscription).where(Subscription.account_id == account.id))
        assert subscription is not None
        assert subscription.plan_id == "trika"


def test_admin_endpoints_are_role_scoped_and_redacted(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, customer_token = create_identity(
            session, settings, name="Customer"  # type: ignore[arg-type]
        )
        _same_account, _admin, admin_token = create_identity(
            session, settings, name="Admin", role="admin"  # type: ignore[arg-type]
        )
    assert client.get("/admin/overview", headers=auth(customer_token)).status_code == 403  # type: ignore[union-attr]
    overview = client.get("/admin/overview", headers=auth(admin_token))  # type: ignore[union-attr]
    assert overview.status_code == 200
    assert overview.json()["raw_message_access"] == "not_available"
    assert overview.json()["live_models"] is False
    settings.live_models_enabled = True  # type: ignore[union-attr]
    overview = client.get("/admin/overview", headers=auth(admin_token))  # type: ignore[union-attr]
    assert overview.json()["live_models"] is True
    runs = client.get("/admin/runs", headers=auth(admin_token))  # type: ignore[union-attr]
    assert runs.status_code == 200
    assert all(row["response"] == "redacted" for row in runs.json())


def test_billing_sandbox_is_not_routed_in_production(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    test_settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(
            session, test_settings, name="Production target"  # type: ignore[arg-type]
        )
    production_settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://example.invalid/db",
        allow_development_auth=False,
        auth_secret="a9f2c7e8b4d61093a5c8e2f7d1b40699",  # noqa: S106
        webhook_secret="7d3b9f1a6c2048e5b7d0a2c4f9e18365",  # noqa: S106
    )
    client.app.dependency_overrides[get_settings] = lambda: production_settings  # type: ignore[union-attr]
    raw = json.dumps(
        {
            "event_id": "production-sandbox-1",
            "account_id": account.id,
            "version": 99,
            "type": "activated",
            "plan_id": "part",
        },
        separators=(",", ":"),
    ).encode()
    response = client.post(  # type: ignore[union-attr]
        "/webhooks/billing-sandbox",
        content=raw,
        headers={
            "X-Signature-SHA256": sign(raw, production_settings.webhook_secret),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 404
    with factory() as session:  # type: ignore[operator]
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        assert subscription.plan_id == "ananta"
