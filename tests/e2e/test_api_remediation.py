import hashlib
import hmac
import json

from sqlalchemy import func, select

from daily_agent.models import (
    Account,
    BillingEvent,
    Note,
    Run,
    Subscription,
    UsagePeriod,
    UsageWindow,
    User,
)
from daily_agent.security import issue_development_token
from tests.conftest import create_identity


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign(raw: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_idempotency_keys_are_scoped_per_account(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _a, _ua, token_a = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        _b, _ub, token_b = create_identity(session, settings, name="B")  # type: ignore[arg-type]
    payload = {"text": "same key, different tenant", "idempotency_key": "shared-key-01"}
    first = client.post("/v1/messages", headers=auth(token_a), json=payload)  # type: ignore[union-attr]
    second = client.post("/v1/messages", headers=auth(token_b), json=payload)  # type: ignore[union-attr]
    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] != second.json()["run_id"]


def test_message_replay_with_different_payload_is_rejected(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
    first = client.post(  # type: ignore[union-attr]
        "/v1/messages",
        headers=auth(token),
        json={"text": "original", "idempotency_key": "dup-key-0001"},
    )
    mismatch = client.post(  # type: ignore[union-attr]
        "/v1/messages",
        headers=auth(token),
        json={"text": "DIFFERENT", "idempotency_key": "dup-key-0001"},
    )
    assert first.status_code == 200
    assert mismatch.status_code == 409
    with factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(Run)) == 1


def test_task_replay_with_different_payload_is_rejected(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
    first = client.post(  # type: ignore[union-attr]
        "/v1/tasks",
        headers=auth(token),
        json={"title": "t1", "idempotency_key": "task-key-0001"},
    )
    replay = client.post(  # type: ignore[union-attr]
        "/v1/tasks",
        headers=auth(token),
        json={"title": "t1", "idempotency_key": "task-key-0001"},
    )
    mismatch = client.post(  # type: ignore[union-attr]
        "/v1/tasks",
        headers=auth(token),
        json={"title": "DIFFERENT", "idempotency_key": "task-key-0001"},
    )
    assert first.status_code == 201
    assert replay.json()["id"] == first.json()["id"]  # type: ignore[call-arg]
    assert mismatch.status_code == 409


def test_notes_accept_optional_idempotency_key(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
    body = {"content": "remember this", "idempotency_key": "note-key-0001"}
    first = client.post("/v1/notes", headers=auth(token), json=body)  # type: ignore[union-attr]
    replay = client.post("/v1/notes", headers=auth(token), json=body)  # type: ignore[union-attr]
    mismatch = client.post(  # type: ignore[union-attr]
        "/v1/notes",
        headers=auth(token),
        json={"content": "DIFFERENT", "idempotency_key": "note-key-0001"},
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]  # type: ignore[call-arg]
    assert mismatch.status_code == 409
    with factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(Note)) == 1


def test_usage_endpoint_does_not_mutate(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        session.query(UsageWindow).delete()
        session.query(UsagePeriod).delete()
        session.commit()
    response = client.get("/v1/usage", headers=auth(token))  # type: ignore[union-attr]
    assert response.status_code == 200
    body = response.json()  # type: ignore[union-attr]
    assert body["everyday_used"] == 0
    assert body["reserved_micro"] == 0 and body["settled_micro"] == 0
    assert "period_reset_at" in body and body["reset_at"] != body["period_reset_at"]
    with factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(UsageWindow)) == 0
        assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 0


def test_complete_task_is_owner_scoped(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account = Account(name="Shared")  # type: ignore[call-arg]
        session.add(account)
        session.flush()
        owner = User(account_id=account.id, display_name="owner", role="customer")
        other = User(account_id=account.id, display_name="other", role="customer")
        session.add_all([owner, other, Subscription(account_id=account.id)])
        session.commit()
        owner_token = issue_development_token(owner, settings)  # type: ignore[arg-type]
        other_token = issue_development_token(other, settings)  # type: ignore[arg-type]
    created = client.post(  # type: ignore[union-attr]
        "/v1/tasks",
        headers=auth(owner_token),
        json={"title": "owner task", "idempotency_key": "owner-task-01"},
    )
    task_id = created.json()["id"]  # type: ignore[union-attr]
    denied = client.patch(f"/v1/tasks/{task_id}/complete", headers=auth(other_token))  # type: ignore[union-attr]
    assert denied.status_code == 404
    allowed = client.patch(f"/v1/tasks/{task_id}/complete", headers=auth(owner_token))  # type: ignore[union-attr]
    assert allowed.status_code == 200


def test_webhook_replay_with_different_payload_is_rejected(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    settings = test_context["settings"]
    raw_a = b'{"message":"one"}'
    raw_b = b'{"message":"two"}'
    headers_a = {
        "X-Event-ID": "evt-dup",
        "X-Signature-SHA256": sign(raw_a, settings.webhook_secret),  # type: ignore[union-attr]
    }
    headers_b = {
        "X-Event-ID": "evt-dup",
        "X-Signature-SHA256": sign(raw_b, settings.webhook_secret),  # type: ignore[union-attr]
    }
    first = client.post("/webhooks/internal-test", content=raw_a, headers=headers_a)  # type: ignore[union-attr]
    mismatch = client.post("/webhooks/internal-test", content=raw_b, headers=headers_b)  # type: ignore[union-attr]
    assert first.status_code == 200
    assert mismatch.status_code == 409


def test_billing_replay_with_different_payload_is_rejected(test_context: dict[str, object]) -> None:
    client = test_context["client"]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]

    def post(payload: dict[str, object]) -> object:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return client.post(  # type: ignore[union-attr]
            "/webhooks/billing-sandbox",
            content=raw,
            headers={
                "X-Signature-SHA256": sign(raw, settings.webhook_secret),  # type: ignore[union-attr]
                "Content-Type": "application/json",
            },
        )

    first = post(
        {"event_id": "evt-1", "account_id": account.id, "version": 1, "type": "activated", "plan_id": "trika"}
    )
    mismatch = post(
        {"event_id": "evt-1", "account_id": account.id, "version": 2, "type": "cancelled", "plan_id": "trika"}
    )
    assert first.json()["accepted"] is True  # type: ignore[union-attr]
    assert mismatch.status_code == 409  # type: ignore[union-attr]
    with factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(BillingEvent)) == 1
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None and subscription.status == "active"
