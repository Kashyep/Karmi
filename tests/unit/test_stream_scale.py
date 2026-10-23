from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from daily_agent.models import ChatMessage, Conversation
from daily_agent.routes import stream as stream_routes
from daily_agent.schemas_chat import ChatStreamRequest
from tests.unit.test_stream_routes import _setup_app


def test_enforce_input_budget_rejects_oversize_text() -> None:
    policy = SimpleNamespace(input_tokens=10)
    with pytest.raises(HTTPException) as exc:
        stream_routes._enforce_input_budget("x" * 400, policy)  # ~100 tokens
    assert exc.value.status_code == 413
    assert exc.value.detail["code"] == "INPUT_TOO_LARGE"
    assert exc.value.detail["max_input_tokens"] == 10


def test_enforce_input_budget_accepts_text_within_budget() -> None:
    policy = SimpleNamespace(input_tokens=1000)
    stream_routes._enforce_input_budget("x" * 400, policy)


def test_chat_stream_schema_caps_text_length() -> None:
    too_long = "x" * 100_001
    with pytest.raises(ValidationError):
        ChatStreamRequest.model_validate({"text": too_long, "clientMessageId": "client-msg-1"})


def test_chat_stream_oversize_returns_413_and_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory, token, account_id, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    tiny_policy = SimpleNamespace(input_tokens=5)
    monkeypatch.setattr(stream_routes, "policy_for", lambda session, account_id: (None, tiny_policy))

    resp = client.post(
        "/v1/chat/stream",
        json={"text": "y" * 2000, "clientMessageId": "client-msg-oversize"},
        headers=headers,
    )
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "INPUT_TOO_LARGE"

    with factory() as session:
        conv_count = session.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.account_id == account_id)
        )
        msg_count = session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.account_id == account_id)
        )
    assert conv_count == 0
    assert msg_count == 0
