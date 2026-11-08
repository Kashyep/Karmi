"""Every path that accepts user text enforces the plan's input budget before reserving anything."""

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from daily_agent import services
from daily_agent.models import ChatMessage
from daily_agent.streaming.registry import get_stream_registry
from tests.unit.test_stream_routes import _parse_sse, _setup_app
from tests.unit.test_stream_scale import _reservation_count

TEXT = "y" * 100  # 25 estimated tokens: fits the default plan, not the tiny one below


def _shrink_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    def tiny_policy_for(session: Any, account_id: str) -> Any:
        subscription, real = services.policy_for(session, account_id)
        return subscription, dataclasses.replace(real, input_tokens=5)

    for module in (
        "daily_agent.api",
        "daily_agent.routes.stream",
        "daily_agent.routes.conversations",
    ):
        monkeypatch.setattr(f"{module}.policy_for", tiny_policy_for)


def test_input_limit_applies_to_every_user_text_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_stream_registry().clear()
    client, factory, token, account_id, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    # Default plan, both carrying TEXT. /v1/messages stores request_hash, which run-regenerate
    # verifies; the stream route does not, so message-id paths use a streamed exchange.
    first = client.post(
        "/v1/messages",
        json={"text": TEXT, "idempotency_key": "idem-key-0001"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    run_id = first.json()["run_id"]

    setup = client.post(
        "/v1/chat/stream",
        json={"text": TEXT, "clientMessageId": "client-msg-limit-setup"},
        headers=headers,
    )
    assert setup.status_code == 200, setup.text
    started = next(e for e in _parse_sse(setup.text) if e["event"] == "run.started")["data"]
    assistant_id = started["assistant_message_id"]
    with factory() as session:
        assistant = session.get(ChatMessage, assistant_id)
        assert assistant is not None
        conversation_id = assistant.conversation_id
        assistant.finish_reason = "length"  # make it continuable
        session.commit()

    _shrink_plan(monkeypatch)
    before = _reservation_count(factory, account_id)

    responses = {
        "POST /v1/messages": client.post(
            "/v1/messages",
            json={"text": TEXT, "idempotency_key": "idem-key-0002"},
            headers=headers,
        ),
        "POST /v1/runs/{id}/regenerate": client.post(
            f"/v1/runs/{run_id}/regenerate",
            json={"text": TEXT, "idempotency_key": "idem-key-0003"},
            headers=headers,
        ),
        "POST /v1/chat/stream": client.post(
            "/v1/chat/stream",
            json={"text": TEXT, "clientMessageId": "client-msg-big"},
            headers=headers,
        ),
        "POST /v1/messages/{id}/continue": client.post(
            f"/v1/messages/{assistant_id}/continue", headers=headers
        ),
        "POST /v1/messages/{id}/regenerate": client.post(
            f"/v1/messages/{assistant_id}/regenerate", headers=headers
        ),
        "POST /v1/tasks": client.post(
            "/v1/tasks",
            json={"title": TEXT, "idempotency_key": "task-key-0001"},
            headers=headers,
        ),
        "POST /v1/reminders": client.post(
            "/v1/reminders",
            json={
                "text": TEXT,
                "due_at": "2030-01-01T10:00:00+00:00",
                "timezone": "UTC",
                "idempotency_key": "reminder-key-0001",
            },
            headers=headers,
        ),
        "PATCH /v1/conversations/{id}": client.patch(
            f"/v1/conversations/{conversation_id}",
            json={"title": "t" * 100},
            headers=headers,
        ),
    }

    for label, resp in responses.items():
        assert resp.status_code == 413, f"{label}: {resp.status_code} {resp.text}"
        assert resp.json()["detail"]["code"] == "INPUT_TOO_LARGE", label
        assert resp.json()["detail"]["max_input_tokens"] == 5, label
    assert _reservation_count(factory, account_id) == before
