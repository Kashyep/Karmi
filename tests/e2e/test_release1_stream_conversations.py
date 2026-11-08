"""Release 1 backend e2e: SSE streaming, run control, and conversation management."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.deps import gateway_dependency
from daily_agent.gateway.types import StreamChunk
from daily_agent.models import ChatMessage, Conversation, Run
from daily_agent.schemas_chat import FinishReason, MessageStatus
from daily_agent.streaming.registry import get_stream_registry
from tests.conftest import create_identity


class _FastGateway:
    live = False

    async def stream(self, **kwargs: object) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="Hello ")
        yield StreamChunk(text="World!")
        yield StreamChunk(text="", finish_reason="stop")


class _SlowGateway:
    """Idles past the 15s heartbeat threshold before answering."""

    live = False

    async def stream(self, **kwargs: object) -> AsyncIterator[StreamChunk]:
        await asyncio.sleep(16.5)
        yield StreamChunk(text="Slow ")
        yield StreamChunk(text="reply", finish_reason="stop")


class _Env:
    def __init__(self, client: TestClient, factory: sessionmaker[Session], settings: Settings) -> None:
        self.client = client
        self.factory = factory
        self.settings = settings


def _build(tmp_path: Path, gateway: object) -> tuple[_Env, dict[str, str]]:
    db_path = tmp_path / "r1_e2e.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{db_path}",
        auth_secret="test-secret-with-enough-entropy-1234",
    )
    with factory() as session:
        _, _, token = create_identity(session, settings, name="Owner")
        _, _, other_token = create_identity(session, settings, name="Intruder")

    app = create_app()

    def session_override() -> Any:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[gateway_dependency] = lambda: gateway
    env = _Env(TestClient(app), factory, settings)
    return env, {
        "owner": f"Bearer {token}",
        "other": f"Bearer {other_token}",
    }


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    get_stream_registry().clear()


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        name = event_id = data = None
        for line in block.strip().split("\n"):
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("id: "):
                event_id = int(line[len("id: ") :])
            elif line.startswith("data: "):
                raw_data = line[len("data: ") :]
                try:
                    data = json.loads(raw_data)
                except ValueError:
                    data = raw_data
        events.append({"event": name, "id": event_id, "data": data})
    return events


def _stream(env: _Env, auth: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    resp = env.client.post("/v1/chat/stream", json=payload, headers={"Authorization": auth})
    assert resp.status_code == 200, resp.text
    return _parse_sse(resp.text)


def _started(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(e["data"] for e in events if e["event"] == "run.started")


def test_sse_happy_path_typed_events_and_finish_reason(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    events = _stream(env, h["owner"], {"text": "What is Python?", "clientMessageId": "happy-msg-0001"})

    names = [e["event"] for e in events]
    assert names[0] == "run.started"
    assert names.count("message.delta") == 2
    assert names[-1] == "run.finished"
    finished = events[-1]["data"]
    assert finished["finish_reason"] == "stop"

    started = _started(events)
    assert started["conversation_id"]
    assert started["run_id"]
    assert started["assistant_message_id"]
    deltas = [e for e in events if e["event"] == "message.delta"]
    assert "".join(d["data"]["text"] for d in deltas) == "Hello World!"
    assert [d["id"] for d in deltas] == sorted(d["id"] for d in deltas)


def test_heartbeat_emitted_during_idle_gap(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _SlowGateway())
    events = _stream(env, h["owner"], {"text": "Slow question", "clientMessageId": "heartbeat-0001"})
    names = [e["event"] for e in events]
    assert "heartbeat" in names
    assert names[-1] == "run.finished"


def test_resume_after_seq_returns_only_later_deltas(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    events = _stream(env, h["owner"], {"text": "Resume me", "clientMessageId": "resume-msg-01"})
    run_id = _started(events)["run_id"]
    all_deltas = [e for e in events if e["event"] == "message.delta"]
    first_id = all_deltas[0]["id"]

    resp = env.client.get(f"/v1/runs/{run_id}/events?after_seq={first_id}", headers={"Authorization": h["owner"]})
    assert resp.status_code == 200
    resumed = _parse_sse(resp.text)
    resumed_deltas = [e for e in resumed if e["event"] == "message.delta"]
    assert [d["id"] for d in resumed_deltas] == [d["id"] for d in all_deltas if d["id"] > first_id]
    assert all(e["event"] != "run.started" for e in resumed)
    assert resumed[-1]["event"] == "run.finished"


def test_stop_marks_message_stopped_and_touches_conversation(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    events = _stream(env, h["owner"], {"text": "Stop me", "clientMessageId": "stop-msg-0001"})
    started = _started(events)
    run_id, conv_id, assistant_id = started["run_id"], started["conversation_id"], started["assistant_message_id"]

    # Simulate an in-flight run that the registry no longer tracks (process-local state lost).
    with env.factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = "streaming"
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        msg.status = MessageStatus.STREAMING.value
        session.commit()
        before = session.get(Conversation, conv_id).updated_at  # type: ignore[union-attr]
    get_stream_registry().clear()

    resp = env.client.post(f"/v1/runs/{run_id}/stop", headers={"Authorization": h["owner"]})
    assert resp.status_code == 202

    with env.factory() as session:
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        assert msg.status == MessageStatus.STOPPED.value
        assert msg.finish_reason == FinishReason.CANCELLED.value
        conv = session.get(Conversation, conv_id)
        assert conv is not None
        assert conv.updated_at >= before


def test_continue_appends_to_truncated_message(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    events = _stream(env, h["owner"], {"text": "Keep going", "clientMessageId": "cont-msg-0001"})
    assistant_id = _started(events)["assistant_message_id"]

    with env.factory() as session:
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        msg.finish_reason = FinishReason.LENGTH.value
        session.commit()

    resp = env.client.post(f"/v1/messages/{assistant_id}/continue", headers={"Authorization": h["owner"]})
    assert resp.status_code == 200
    cont = _parse_sse(resp.text)
    assert cont[-1]["event"] == "run.finished"

    with env.factory() as session:
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        assert msg.content.startswith("Hello World!")
        assert len(msg.content) > len("Hello World!")


def test_regenerate_creates_sibling_variant(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    events = _stream(env, h["owner"], {"text": "Poem please", "clientMessageId": "regen-msg-01"})
    assistant_id = _started(events)["assistant_message_id"]

    resp = env.client.post(f"/v1/messages/{assistant_id}/regenerate", headers={"Authorization": h["owner"]})
    assert resp.status_code == 200
    sibling_id = _started(_parse_sse(resp.text))["assistant_message_id"]
    assert sibling_id != assistant_id

    with env.factory() as session:
        orig = session.get(ChatMessage, assistant_id)
        sibling = session.get(ChatMessage, sibling_id)
        assert orig is not None and sibling is not None
        assert sibling.parent_message_id == orig.parent_message_id
        assert sibling.variant_index == orig.variant_index + 1


def test_idempotent_client_message_id_replays_same_run(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    payload = {"text": "Once only", "clientMessageId": "idem-msg-0001"}
    first = _started(_stream(env, h["owner"], payload))
    second = _started(_stream(env, h["owner"], payload))
    assert first["run_id"] == second["run_id"]
    assert first["conversation_id"] == second["conversation_id"]

    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "user")) == 1


def test_conversation_created_only_on_first_message(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())

    # Unknown conversation id: rejected and nothing persisted.
    resp = env.client.post(
        "/v1/chat/stream",
        json={"text": "Ghost", "conversationId": "does-not-exist", "clientMessageId": "ghost-msg-01"},
        headers={"Authorization": h["owner"]},
    )
    assert resp.status_code == 404
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Conversation)) == 0

    first = _started(_stream(env, h["owner"], {"text": "First ever", "clientMessageId": "first-msg-001"}))
    conv_id = first["conversation_id"]
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1

    _stream(
        env,
        h["owner"],
        {"text": "Second turn", "conversationId": conv_id, "clientMessageId": "second-msg-01"},
    )
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1
        conv = session.get(Conversation, conv_id)
        assert conv is not None and conv.title == "First ever"


def test_search_by_title_and_content(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    _stream(env, h["owner"], {"text": "Zebra migration routes", "clientMessageId": "search-msg-01"})

    by_title = env.client.get("/v1/conversations/search?q=zebra", headers={"Authorization": h["owner"]})
    assert by_title.status_code == 200
    results = by_title.json()
    assert len(results) == 1
    assert results[0]["matched"] == "title"

    by_content = env.client.get("/v1/conversations/search?q=World", headers={"Authorization": h["owner"]})
    assert by_content.status_code == 200
    content_hits = by_content.json()
    assert len(content_hits) == 1
    assert content_hits[0]["matched"] == "content"

    empty = env.client.get("/v1/conversations/search?q=nomatchtoken", headers={"Authorization": h["owner"]})
    assert empty.json() == []


def test_archive_delete_restore_lifecycle(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    conv_id = _started(_stream(env, h["owner"], {"text": "Lifecycle", "clientMessageId": "life-msg-0001"}))[
        "conversation_id"
    ]
    auth = {"Authorization": h["owner"]}

    resp = env.client.patch(f"/v1/conversations/{conv_id}", json={"archived": True}, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["archivedAt"] is not None
    active = env.client.get("/v1/conversations", headers=auth).json()["items"]
    assert conv_id not in [c["id"] for c in active]
    archived = env.client.get("/v1/conversations?archived=true", headers=auth).json()["items"]
    assert conv_id in [c["id"] for c in archived]

    assert env.client.delete(f"/v1/conversations/{conv_id}", headers=auth).status_code == 204
    assert env.client.get(f"/v1/conversations/{conv_id}", headers=auth).status_code == 404

    restored = env.client.post(f"/v1/conversations/{conv_id}/restore", headers=auth)
    assert restored.status_code == 200
    assert env.client.get(f"/v1/conversations/{conv_id}", headers=auth).status_code == 200


def test_cross_user_access_is_not_found(tmp_path: Path) -> None:
    env, h = _build(tmp_path, _FastGateway())
    events = _stream(env, h["owner"], {"text": "Private", "clientMessageId": "private-msg-1"})
    started = _started(events)
    conv_id, run_id = started["conversation_id"], started["run_id"]
    other = {"Authorization": h["other"]}

    assert env.client.get(f"/v1/conversations/{conv_id}", headers=other).status_code == 404
    assert env.client.get(f"/v1/conversations/{conv_id}/messages", headers=other).status_code == 404
    assert env.client.patch(f"/v1/conversations/{conv_id}", json={"pinned": True}, headers=other).status_code == 404
    assert env.client.delete(f"/v1/conversations/{conv_id}", headers=other).status_code == 404
    assert env.client.get(f"/v1/runs/{run_id}/events", headers=other).status_code == 404
    assert env.client.post(f"/v1/runs/{run_id}/stop", headers=other).status_code == 404
    assert env.client.get("/v1/conversations/search?q=Private", headers=other).json() == []
