import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from daily_agent.models import BudgetReservation, ChatMessage, Conversation, Run
from daily_agent.routes import stream as stream_routes
from daily_agent.schemas_chat import ChatStreamRequest
from daily_agent.streaming.registry import get_stream_registry
from tests.unit.test_stream_routes import _parse_sse, _setup_app


def _tiny_policy(
    monkeypatch: pytest.MonkeyPatch, delay: float = 0.0, input_tokens: int = 5
) -> None:
    policy = SimpleNamespace(input_tokens=input_tokens, output_tokens=64, price_inr=0)

    def fake_policy_for(session: Any, account_id: str) -> tuple[None, SimpleNamespace]:
        if delay:
            time.sleep(delay)  # simulates a slow synchronous DB call
        return None, policy

    monkeypatch.setattr(stream_routes, "policy_for", fake_policy_for)


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
    _tiny_policy(monkeypatch)

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


def test_slow_db_call_does_not_block_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five concurrent requests each doing a 0.5s synchronous call must overlap, not serialize."""
    client, _factory, token, _, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    _tiny_policy(monkeypatch, delay=0.5)

    async def fire_all() -> list[int]:
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

            async def one(i: int) -> int:
                resp = await ac.post(
                    "/v1/chat/stream",
                    json={"text": "y" * 2000, "clientMessageId": f"client-msg-slow-{i}"},
                    headers=headers,
                )
                return resp.status_code

            return list(await asyncio.gather(*(one(i) for i in range(5))))

    started = time.monotonic()
    statuses = asyncio.run(fire_all())
    elapsed = time.monotonic() - started

    assert statuses == [413] * 5
    assert elapsed < 1.5, f"requests serialized on the event loop: {elapsed:.2f}s"


def _first_chat(client: Any, headers: dict[str, str], client_message_id: str) -> dict[str, Any]:
    resp = client.post(
        "/v1/chat/stream",
        json={"text": "Hello there", "clientMessageId": client_message_id},
        headers=headers,
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    return next(e for e in events if e["event"] == "run.started")["data"]


def _reservation_count(factory: Any, account_id: str) -> int:
    with factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(BudgetReservation)
                .where(BudgetReservation.account_id == account_id)
            )
            or 0
        )


def test_regenerate_duplicate_replays_existing_run_without_reservation(
    tmp_path: Path,
) -> None:
    get_stream_registry().clear()
    client, factory, token, account_id, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    started = _first_chat(client, headers, "client-msg-regen-dup")
    run_id = started["run_id"]
    assistant_id = started["assistant_message_id"]
    user_id = started["user_message_id"]

    # The run already owns the variant slot a regenerate would claim (a concurrent or retried
    # request): the regenerate must replay it and reserve nothing new.
    with factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.logical_request_id = stream_routes._regen_key(user_id, 1)
        session.commit()

    before = _reservation_count(factory, account_id)
    resp = client.post(f"/v1/messages/{assistant_id}/regenerate", headers=headers)
    assert resp.status_code == 200
    names = [e["event"] for e in _parse_sse(resp.text)]
    assert "run.started" in names and "run.finished" in names
    assert _reservation_count(factory, account_id) == before


def test_continue_inflight_duplicate_replays_without_reservation(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, account_id, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    started = _first_chat(client, headers, "client-msg-cont-dup")
    prev_run_id = started["run_id"]
    assistant_id = started["assistant_message_id"]

    # Simulate a continue already in flight: message is streaming under a continuation run
    # whose logical key matches what the duplicate continue request would compute.
    new_run_id = "run_inflight_continue"
    with factory() as session:
        prev = session.get(Run, prev_run_id)
        assert prev is not None
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        msg.status = "streaming"
        msg.run_id = new_run_id
        msg.finish_reason = None
        session.add(
            Run(
                id=new_run_id,
                account_id=prev.account_id,
                user_id=prev.user_id,
                logical_request_id=stream_routes._continue_key(assistant_id, prev_run_id),
                status="streaming",
                continuation_of_run_id=prev_run_id,
                last_seq=0,
                heartbeat_at=datetime.now(UTC),
            )
        )
        session.commit()

    before = _reservation_count(factory, account_id)
    resp = client.post(f"/v1/messages/{assistant_id}/continue", headers=headers)
    assert resp.status_code == 200
    names = [e["event"] for e in _parse_sse(resp.text)]
    assert "run.started" in names
    assert _reservation_count(factory, account_id) == before
