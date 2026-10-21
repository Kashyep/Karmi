import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.deps import gateway_dependency
from daily_agent.gateway.types import StreamChunk
from daily_agent.models import ChatMessage, Conversation
from daily_agent.schemas_chat import FinishReason, MessageStatus
from daily_agent.streaming.registry import get_stream_registry
from tests.conftest import create_identity


class MockStreamingGateway:
    live = False

    async def stream(self, **kwargs: object) -> Any:
        yield StreamChunk(text="Hello ")
        yield StreamChunk(text="World!")
        yield StreamChunk(text="", finish_reason="stop")


def _setup_app(tmp_path: Path) -> tuple[TestClient, sessionmaker, str, str, str]:
    db_path = tmp_path / "stream_routes_test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{db_path}",
        auth_secret="test-secret-with-enough-entropy-1234",
    )

    with factory() as session:
        account, user, token = create_identity(session, settings, name="TestUser")
        account_id, user_id = account.id, user.id

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[gateway_dependency] = lambda: MockStreamingGateway()

    client = TestClient(app)
    return client, factory, token, account_id, user_id


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    blocks = raw.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_name = None
        event_id = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("id: "):
                event_id = int(line[len("id: ") :])
            elif line.startswith("data: "):
                data_str = line[len("data: ") :]
                try:
                    data = json.loads(data_str)
                except Exception:
                    data = data_str
        events.append({"event": event_name, "id": event_id, "data": data})
    return events


def test_chat_stream_happy_path_and_idempotency(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "text": "What is Python?",
        "clientMessageId": "client-msg-12345",
    }
    resp = client.post("/v1/chat/stream", json=payload, headers=headers)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    event_names = [e["event"] for e in events]
    assert "run.started" in event_names
    assert "message.delta" in event_names
    assert "run.finished" in event_names

    run_started = next(e for e in events if e["event"] == "run.started")
    conv_id = run_started["data"]["conversation_id"]
    run_id = run_started["data"]["run_id"]

    # Idempotent replay: send same request again
    resp2 = client.post("/v1/chat/stream", json=payload, headers=headers)
    assert resp2.status_code == 200
    events2 = _parse_sse(resp2.text)
    run_started2 = next(e for e in events2 if e["event"] == "run.started")
    assert run_started2["data"]["conversation_id"] == conv_id
    assert run_started2["data"]["run_id"] == run_id

    # Verify DB has exactly one user message and one conversation
    with factory() as session:
        convs = session.scalars(select(Conversation)).all()
        assert len(convs) == 1
        msgs = session.scalars(select(ChatMessage).where(ChatMessage.role == "user")).all()
        assert len(msgs) == 1


def test_resume_events_after_seq(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, _, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/v1/chat/stream",
        json={"text": "Hello", "clientMessageId": "client-msg-resume"},
        headers=headers,
    )
    events = _parse_sse(resp.text)
    run_id = events[0]["data"]["run_id"]

    # Resume after_seq=1 -> skips delta seq 1, returns delta seq 2 and run.finished
    resp_resume = client.get(f"/v1/runs/{run_id}/events?after_seq=1", headers=headers)
    assert resp_resume.status_code == 200
    resume_events = _parse_sse(resp_resume.text)
    for evt in resume_events:
        if evt["event"] == "message.delta":
            assert evt["id"] > 1
        assert evt["event"] != "run.started"


def test_resume_unavailable_when_evicted(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/v1/chat/stream",
        json={"text": "Test eviction", "clientMessageId": "client-msg-evict"},
        headers=headers,
    )
    events = _parse_sse(resp.text)
    run_id = events[0]["data"]["run_id"]

    # Evict registry
    get_stream_registry().clear()

    resp_resume = client.get(f"/v1/runs/{run_id}/events?after_seq=0", headers=headers)
    assert resp_resume.status_code == 200
    resume_events = _parse_sse(resp_resume.text)
    assert len(resume_events) == 1
    assert resume_events[0]["event"] == "run.error"
    assert resume_events[0]["data"]["category"] == "resume_unavailable"
    assert resume_events[0]["data"]["retryable"] is False


def test_stop_run_202(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/v1/chat/stream",
        json={"text": "Stop me", "clientMessageId": "client-msg-stop"},
        headers=headers,
    )
    events = _parse_sse(resp.text)
    run_id = events[0]["data"]["run_id"]

    resp_stop = client.post(f"/v1/runs/{run_id}/stop", headers=headers)
    assert resp_stop.status_code == 202
    assert resp_stop.json()["status"] == "cancelled"


def test_continue_validation_and_execution(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/v1/chat/stream",
        json={"text": "Explain quantum physics", "clientMessageId": "client-msg-cont"},
        headers=headers,
    )
    events = _parse_sse(resp.text)
    run_started = next(e for e in events if e["event"] == "run.started")
    assistant_id = run_started["data"]["assistant_message_id"]

    # Message finished normally with finish_reason='stop' -> continue must fail with 400
    resp_invalid = client.post(f"/v1/messages/{assistant_id}/continue", headers=headers)
    assert resp_invalid.status_code == 400

    # Mark message as interrupted / length to allow continue
    with factory() as session:
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        msg.finish_reason = FinishReason.LENGTH.value
        msg.status = MessageStatus.COMPLETE.value
        session.commit()

    # Now continue should succeed
    resp_cont = client.post(f"/v1/messages/{assistant_id}/continue", headers=headers)
    assert resp_cont.status_code == 200
    cont_events = _parse_sse(resp_cont.text)
    cont_names = [e["event"] for e in cont_events]
    assert "run.started" in cont_names
    assert "message.delta" in cont_names
    assert "run.finished" in cont_names


def test_regenerate_message(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/v1/chat/stream",
        json={"text": "Write a poem", "clientMessageId": "client-msg-regen"},
        headers=headers,
    )
    events = _parse_sse(resp.text)
    run_started = next(e for e in events if e["event"] == "run.started")
    assistant_id = run_started["data"]["assistant_message_id"]

    resp_regen = client.post(f"/v1/messages/{assistant_id}/regenerate", headers=headers)
    assert resp_regen.status_code == 200
    regen_events = _parse_sse(resp_regen.text)
    regen_started = next(e for e in regen_events if e["event"] == "run.started")
    sibling_id = regen_started["data"]["assistant_message_id"]
    assert sibling_id != assistant_id

    # Verify sibling message variant_index
    with factory() as session:
        orig = session.get(ChatMessage, assistant_id)
        sibling = session.get(ChatMessage, sibling_id)
        assert orig is not None and sibling is not None
        assert sibling.parent_message_id == orig.parent_message_id
        assert sibling.variant_index == orig.variant_index + 1
