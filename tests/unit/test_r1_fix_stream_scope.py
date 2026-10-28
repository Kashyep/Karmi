from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.models import (
    Account,
    ChatMessage,
    Conversation,
    Run,
    User,
    chat_message_id_str,
    utcnow,
    uuid_str,
)
from daily_agent.schemas_chat import FinishReason
from daily_agent.security import issue_development_token
from daily_agent.streaming.registry import RunState, StreamEvent, get_stream_registry
from tests.conftest import create_identity


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
                try:
                    event_id = int(line[len("id: ") :])
                except ValueError:
                    event_id = line[len("id: ") :]
            elif line.startswith("data: "):
                data_str = line[len("data: ") :]
                try:
                    data = json.loads(data_str)
                except Exception:
                    data = data_str
        events.append({"event": event_name, "id": event_id, "data": data})
    return events


def _setup_scope_env(
    tmp_path: Path,
) -> tuple[TestClient, sessionmaker, Settings, Account, User, str, User, str]:
    db_path = tmp_path / "scope_test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{db_path}",
        auth_secret="test-secret-with-sufficient-entropy-12345",
    )

    with factory() as session:
        account, user_a, token_a = create_identity(session, settings, name="UserA")
        user_b = User(account_id=account.id, display_name="UserB", role="customer")
        session.add(user_b)
        session.commit()
        token_b = issue_development_token(user_b, settings)

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings

    client = TestClient(app)
    return client, factory, settings, account, user_a, token_a, user_b, token_b


def test_cross_user_continue_returns_404(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, user_b, token_b = _setup_scope_env(tmp_path)
    # User B owns conversation and assistant message
    with factory() as session:
        conv_b = Conversation(account_id=account.id, user_id=user_b.id, title="B title")
        session.add(conv_b)
        session.flush()
        msg_u = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv_b.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Hello from B",
        )
        msg_a = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv_b.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Reply to B",
            finish_reason=FinishReason.LENGTH.value,
            parent_message_id=msg_u.id,
            variant_index=0,
        )
        session.add_all([msg_u, msg_a])
        session.commit()
        assistant_id = msg_a.id

    # User A tries to continue User B's message -> 404
    resp = client.post(
        f"/v1/messages/{assistant_id}/continue",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "message not found"


def test_cross_user_regenerate_returns_404(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, user_b, token_b = _setup_scope_env(tmp_path)
    with factory() as session:
        conv_b = Conversation(account_id=account.id, user_id=user_b.id, title="B title")
        session.add(conv_b)
        session.flush()
        msg_u = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv_b.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Hello from B",
        )
        msg_a = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv_b.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Reply to B",
            finish_reason=FinishReason.STOP.value,
            parent_message_id=msg_u.id,
            variant_index=0,
        )
        session.add_all([msg_u, msg_a])
        session.commit()
        assistant_id = msg_a.id

    # User A tries to regenerate User B's message -> 404
    resp = client.post(
        f"/v1/messages/{assistant_id}/regenerate",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "message not found"


def test_cross_user_stop_returns_404(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, user_b, token_b = _setup_scope_env(tmp_path)
    run_id = uuid_str()
    with factory() as session:
        run_b = Run(
            id=run_id,
            account_id=account.id,
            user_id=user_b.id,
            logical_request_id="req-stop-b",
            status="streaming",
        )
        session.add(run_b)
        session.commit()

    # User A tries to stop User B's run -> 404
    resp = client.post(
        f"/v1/runs/{run_id}/stop",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404


def test_cross_user_events_returns_404(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, user_b, token_b = _setup_scope_env(tmp_path)
    run_id = uuid_str()
    with factory() as session:
        run_b = Run(
            id=run_id,
            account_id=account.id,
            user_id=user_b.id,
            logical_request_id="req-events-b",
            status="completed",
            last_seq=2,
        )
        session.add(run_b)
        session.commit()

    # User A tries to access User B's run events -> 404
    resp = client.get(
        f"/v1/runs/{run_id}/events",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404


def test_cross_user_idempotent_replay_isolation(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, user_b, token_b = _setup_scope_env(tmp_path)
    client_msg_id = "cmid-secret-12345"
    with factory() as session:
        conv_b = Conversation(account_id=account.id, user_id=user_b.id, title="B Secret Conv")
        session.add(conv_b)
        session.flush()
        msg_u = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv_b.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="User B private text",
            client_message_id=client_msg_id,
        )
        msg_a = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv_b.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Secret answer for B",
            parent_message_id=msg_u.id,
        )
        session.add_all([msg_u, msg_a])
        session.commit()
        conv_b_id = conv_b.id

    # 1. User A sends chat_stream with User B's conversation_id -> 404
    resp = client.post(
        "/v1/chat/stream",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "conversation_id": conv_b_id,
            "text": "Try eavesdropping",
            "client_message_id": client_msg_id,
        },
    )
    assert resp.status_code == 404

    # 2. User A sends chat_stream without conversation_id but with User B's client_message_id
    # Must NOT replay User B's run
    resp2 = client.post(
        "/v1/chat/stream",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "text": "My own new question",
            "client_message_id": client_msg_id,
        },
    )
    assert resp2.status_code == 200
    events = _parse_sse(resp2.text)
    started = next(e for e in events if e["event"] == "run.started")
    assert started["data"]["conversation_id"] != conv_b_id


def test_soft_deleted_conversation_continue_and_regenerate_return_404(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, _, _ = _setup_scope_env(tmp_path)
    with factory() as session:
        conv = Conversation(
            account_id=account.id,
            user_id=user_a.id,
            title="Soft Deleted Conv",
            deleted_at=utcnow(),
        )
        session.add(conv)
        session.flush()
        msg_u = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="User A text",
        )
        msg_a = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Assistant text",
            finish_reason=FinishReason.LENGTH.value,
            parent_message_id=msg_u.id,
            variant_index=0,
        )
        session.add_all([msg_u, msg_a])
        session.commit()
        assistant_id = msg_a.id

    # Continue on soft-deleted conversation -> 404
    resp_cont = client.post(
        f"/v1/messages/{assistant_id}/continue",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_cont.status_code == 404

    # Regenerate on soft-deleted conversation -> 404
    resp_regen = client.post(
        f"/v1/messages/{assistant_id}/regenerate",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_regen.status_code == 404


def test_run_events_after_seq_beyond_last_seq_emits_resume_unavailable(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, _, _ = _setup_scope_env(tmp_path)
    run_id = uuid_str()
    with factory() as session:
        run = Run(
            id=run_id,
            account_id=account.id,
            user_id=user_a.id,
            logical_request_id="req-seq-test",
            status="completed",
            last_seq=2,
        )
        session.add(run)
        session.commit()

    run_state = RunState(
        run_id=run_id,
        conversation_id="conv-1",
        user_message_id="msg-u",
        assistant_message_id="msg-a",
    )
    run_state.last_seq = 2
    run_state.terminal = True
    run_state.events = [
        StreamEvent(event="run.started", data={}, seq=0),
        StreamEvent(event="message.delta", data={"text": "hello"}, seq=1),
        StreamEvent(event="message.delta", data={"text": "world"}, seq=2),
        StreamEvent(event="run.finished", data={"finish_reason": "stop"}, seq=None),
    ]
    registry = get_stream_registry()
    registry.register(run_state)

    # Client requests after_seq=10 (beyond last_seq=2)
    resp = client.get(
        f"/v1/runs/{run_id}/events?after_seq=10",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert len(events) == 1
    assert events[0]["event"] == "run.error"
    assert events[0]["data"]["category"] == "resume_unavailable"
    assert events[0]["data"]["retryable"] is False


def test_resumed_stream_does_not_replay_historical_heartbeats(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, _, _ = _setup_scope_env(tmp_path)
    run_id = uuid_str()
    with factory() as session:
        run = Run(
            id=run_id,
            account_id=account.id,
            user_id=user_a.id,
            logical_request_id="req-hb-test",
            status="completed",
            last_seq=3,
        )
        session.add(run)
        session.commit()

    run_state = RunState(
        run_id=run_id,
        conversation_id="conv-hb",
        user_message_id="msg-u",
        assistant_message_id="msg-a",
    )
    run_state.last_seq = 3
    run_state.terminal = True
    run_state.events = [
        StreamEvent(event="run.started", data={}, seq=0),
        StreamEvent(event="heartbeat", data={"at": "2026-10-21T10:00:00Z"}, seq=None),
        StreamEvent(event="message.delta", data={"text": "one"}, seq=1),
        StreamEvent(event="heartbeat", data={"at": "2026-10-21T10:00:15Z"}, seq=None),
        StreamEvent(event="message.delta", data={"text": "two"}, seq=2),
        StreamEvent(event="message.delta", data={"text": "three"}, seq=3),
        StreamEvent(event="run.finished", data={"finish_reason": "stop"}, seq=None),
    ]
    registry = get_stream_registry()
    registry.register(run_state)

    # Resuming after_seq=1
    resp = client.get(
        f"/v1/runs/{run_id}/events?after_seq=1",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [e["event"] for e in events]
    # Must NOT contain heartbeat events in resumed catch-up
    assert "heartbeat" not in event_names
    # Must contain delta 2, delta 3, and run.finished
    assert "message.delta" in event_names
    assert "run.finished" in event_names
    deltas = [e for e in events if e["event"] == "message.delta"]
    assert [d["id"] for d in deltas] == [2, 3]


def test_idempotency_without_conversation_id_orders_by_created_at_desc(tmp_path: Path) -> None:
    client, factory, settings, account, user_a, token_a, _, _ = _setup_scope_env(tmp_path)
    client_msg_id = "cmid-multi-row-check"
    with factory() as session:
        conv1 = Conversation(account_id=account.id, user_id=user_a.id, title="Thread 1")
        conv2 = Conversation(account_id=account.id, user_id=user_a.id, title="Thread 2")
        session.add_all([conv1, conv2])
        session.flush()

        run1_id = uuid_str()
        run2_id = uuid_str()
        run1 = Run(id=run1_id, account_id=account.id, user_id=user_a.id, logical_request_id="req1", status="completed")
        run2 = Run(id=run2_id, account_id=account.id, user_id=user_a.id, logical_request_id="req2", status="completed")
        msg1 = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv1.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Msg in thread 1",
            client_message_id=client_msg_id,
            run_id=run1_id,
            created_at=utcnow() - timedelta(minutes=5),
        )
        msg1_a = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv1.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Reply 1",
            run_id=run1_id,
            parent_message_id=msg1.id,
        )
        msg2 = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv2.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Msg in thread 2",
            client_message_id=client_msg_id,
            run_id=run2_id,
            created_at=utcnow(),
        )
        msg2_a = ChatMessage(
            id=chat_message_id_str(),
            conversation_id=conv2.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Reply 2",
            run_id=run2_id,
            parent_message_id=msg2.id,
        )
        session.add_all([run1, run2, msg1, msg1_a, msg2, msg2_a])
        session.commit()

    resp = client.post(
        "/v1/chat/stream",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "text": "Repeated send",
            "client_message_id": client_msg_id,
        },
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    started = next(e for e in events if e["event"] == "run.started")
    # Must match the newer thread (conv2)
    assert started["data"]["conversation_id"] == conv2.id
