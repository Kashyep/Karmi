"""Reply ratings, regenerate links and their sanitized telemetry export."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.config import Settings
from daily_agent.models import MessageFeedback, Run
from daily_agent.parakh.telemetry import build_telemetry_batch
from tests.conftest import create_identity

TEXT = "Explain photosynthesis simply, my roll number is 4821"


def _login(ctx: dict[str, object], name: str) -> dict[str, str]:
    factory = ctx["factory"]
    settings = ctx["settings"]
    assert isinstance(factory, sessionmaker)
    assert isinstance(settings, Settings)
    with factory() as session:
        _account, _user, token = create_identity(session, settings, name=name)
    return {"Authorization": f"Bearer {token}"}


def _client(ctx: dict[str, object]) -> TestClient:
    client = ctx["client"]
    assert isinstance(client, TestClient)
    return client


def _send(ctx: dict[str, object], headers: dict[str, str], key: str) -> dict[str, Any]:
    response = _client(ctx).post(
        "/v1/messages", json={"text": TEXT, "idempotency_key": key}, headers=headers
    )
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _rows(ctx: dict[str, object]) -> list[MessageFeedback]:
    factory = ctx["factory"]
    assert isinstance(factory, sessionmaker)
    with factory() as session:
        return list(session.scalars(select(MessageFeedback)))


def test_rating_is_an_idempotent_upsert_and_reason_only_applies_to_thumbs_down(
    test_context: dict[str, object],
) -> None:
    headers = _login(test_context, "A")
    run_id = _send(test_context, headers, "feedback-run-0001")["run_id"]
    url = f"/v1/runs/{run_id}/feedback"
    client = _client(test_context)

    down = {"rating": "down", "reason": "wrong"}
    first = client.post(url, json=down, headers=headers)
    again = client.post(url, json=down, headers=headers)

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json() == {"run_id": run_id, "rating": "down", "reason": "wrong"}
    assert len(_rows(test_context)) == 1

    changed = client.post(url, json={"rating": "up", "reason": "wrong"}, headers=headers)

    assert changed.json() == {"run_id": run_id, "rating": "up", "reason": None}
    [row] = _rows(test_context)
    assert (row.rating, row.reason) == ("up", None)


def test_free_text_reasons_are_rejected(test_context: dict[str, object]) -> None:
    headers = _login(test_context, "A")
    run_id = _send(test_context, headers, "feedback-run-0002")["run_id"]

    response = _client(test_context).post(
        f"/v1/runs/{run_id}/feedback",
        json={"rating": "down", "reason": "call me on 9876543210"},
        headers=headers,
    )

    assert response.status_code == 422
    assert _rows(test_context) == []


def test_feedback_and_regenerate_are_account_scoped(test_context: dict[str, object]) -> None:
    owner = _login(test_context, "Owner")
    other = _login(test_context, "Other")
    run_id = _send(test_context, owner, "feedback-run-0003")["run_id"]
    client = _client(test_context)

    rate = client.post(f"/v1/runs/{run_id}/feedback", json={"rating": "up"}, headers=other)
    regenerate = client.post(
        f"/v1/runs/{run_id}/regenerate",
        json={"text": TEXT, "idempotency_key": "regen-other-0001"},
        headers=other,
    )

    assert rate.status_code == regenerate.status_code == 404
    assert _rows(test_context) == []


def test_regenerate_links_a_new_reply_to_the_previous_one(test_context: dict[str, object]) -> None:
    headers = _login(test_context, "A")
    first = _send(test_context, headers, "feedback-run-0004")
    client = _client(test_context)
    payload = {"text": TEXT, "idempotency_key": "regen-0004-key1", "reason": "unclear"}

    regenerated = client.post(
        f"/v1/runs/{first['run_id']}/regenerate", json=payload, headers=headers
    )
    replay = client.post(f"/v1/runs/{first['run_id']}/regenerate", json=payload, headers=headers)

    body = regenerated.json()
    assert regenerated.status_code == 200
    assert body["run_id"] != first["run_id"]
    assert body["previous_run_id"] == first["run_id"]
    assert replay.json() == body, "same idempotency key replays the same regenerated reply"
    factory = test_context["factory"]
    assert isinstance(factory, sessionmaker)
    with factory() as session:
        run = session.get(Run, body["run_id"])
        assert run is not None
        assert (run.previous_run_id, run.regenerate_reason) == (first["run_id"], "unclear")
        assert session.scalar(select(func.count()).select_from(Run)) == 2


def test_regenerate_rejects_a_different_prompt_and_a_reused_key(
    test_context: dict[str, object],
) -> None:
    headers = _login(test_context, "A")
    first = _send(test_context, headers, "feedback-run-0005")
    client = _client(test_context)
    url = f"/v1/runs/{first['run_id']}/regenerate"

    mismatch = client.post(
        url,
        json={"text": "A different question", "idempotency_key": "regen-0005-key1"},
        headers=headers,
    )
    reused = client.post(
        url, json={"text": TEXT, "idempotency_key": "feedback-run-0005"}, headers=headers
    )

    assert mismatch.status_code == 409
    assert reused.status_code == 422


def test_export_carries_sanitized_rating_and_retry_feedback(
    test_context: dict[str, object],
) -> None:
    headers = _login(test_context, "A")
    first = _send(test_context, headers, "feedback-run-0006")
    client = _client(test_context)
    client.post(
        f"/v1/runs/{first['run_id']}/feedback",
        json={"rating": "down", "reason": "wrong"},
        headers=headers,
    )
    client.post(
        f"/v1/runs/{first['run_id']}/regenerate",
        json={"text": TEXT, "idempotency_key": "regen-0006-key1", "reason": "wrong"},
        headers=headers,
    )
    factory = test_context["factory"]
    assert isinstance(factory, sessionmaker)
    session: Session
    with factory() as session:
        batch = build_telemetry_batch(
            session,
            start=datetime.now(UTC) - timedelta(days=1),
            end=datetime.now(UTC) + timedelta(days=1),
        )

    assert len(batch["runs"]) == 2
    original = next(r for r in batch["runs"] if r["outcome"]["user_retry_signal"])
    types = sorted(item["feedback_type"] for item in original["feedback"])
    assert types == ["rating", "retry"]
    rating = next(i for i in original["feedback"] if i["feedback_type"] == "rating")
    assert (rating["sanitized_corrected_value"], rating["correction_kind_hint"]) == (
        "down",
        "wrong",
    )
    assert original["outcome"]["user_accept_signal"] is False
    child = next(r for r in batch["runs"] if r is not original)
    assert child["feedback"] == []
    text = json.dumps(batch)
    assert "roll number" not in text and "4821" not in text


def test_per_user_rate_limit_returns_429_with_retry_after(test_context: dict[str, object]) -> None:
    settings = test_context["settings"]
    assert isinstance(settings, Settings)
    settings.rate_limit_per_minute = 3
    busy = _login(test_context, "Busy")
    calm = _login(test_context, "Calm")
    client = _client(test_context)

    statuses = [
        client.post(
            "/v1/messages",
            json={"text": TEXT, "idempotency_key": f"rate-limit-{i:04d}"},
            headers=busy,
        )
        for i in range(5)
    ]

    assert [r.status_code for r in statuses] == [200, 200, 200, 429, 429]
    assert int(statuses[3].headers["retry-after"]) >= 1
    assert statuses[3].json()["detail"]["code"] == "RATE_LIMITED"
    other = client.post(
        "/v1/messages", json={"text": TEXT, "idempotency_key": "calm-0001"}, headers=calm
    )
    assert other.status_code == 200, "the limit is per user"
