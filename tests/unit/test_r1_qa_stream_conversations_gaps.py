from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import daily_agent.streaming.runner
from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.conversations.service import (
    list_conversations,
    search_conversations,
)
from daily_agent.db import Base, get_session
from daily_agent.gateway.types import StreamChunk, TaskType
from daily_agent.models import (
    Account,
    BudgetReservation,
    ChatMessage,
    Conversation,
    ReservationStatus,
    Run,
    RunStatus,
    User,
    utcnow,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.providers import ProviderCall
from daily_agent.schemas_chat import FinishReason, MessageStatus
from daily_agent.security import Principal
from daily_agent.services import reserve_budget
from daily_agent.streaming.registry import (
    RunState,
    get_stream_registry,
)
from daily_agent.streaming.runner import StreamRunner, start_stream_run
from tests.conftest import create_identity


class DelayableGateway:
    """Mock gateway that yields chunks with optional delay between them."""

    def __init__(
        self,
        chunks: list[StreamChunk],
        delay: float = 0.0,
        fail_after_chunks: int | None = None,
        fail_exception: Exception | None = None,
    ) -> None:
        self.chunks = chunks
        self.delay = delay
        self.fail_after_chunks = fail_after_chunks
        self.fail_exception = fail_exception or RuntimeError("Gateway provider crash")

    async def stream(self, **kwargs: object) -> AsyncIterator[StreamChunk]:
        for idx, chunk in enumerate(self.chunks):
            if self.fail_after_chunks is not None and idx >= self.fail_after_chunks:
                raise self.fail_exception
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            yield chunk


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


def _setup_test_env(tmp_path: Path) -> tuple[TestClient, sessionmaker, Settings, Account, User, str]:
    db_path = tmp_path / "gap_test.db"
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
        account, user, token = create_identity(session, settings, name="TestUser")

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings

    client = TestClient(app)
    return client, factory, settings, account, user, token


# ============================================================================
# (a) Stream runner / registry tests
# ============================================================================


def test_client_disconnect_does_not_cancel_generation_and_persists_partial() -> None:
    """Client disconnect (cancelling consumer iterator) does NOT cancel runner generation.

    The runner continues in background until terminal, and all partial text is persisted.
    """
    async def _test() -> None:
        from daily_agent.routes.stream import stream_run_events

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            account = Account(name="DisconnectAcc")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="DisconnectUser")
            session.add(user)
            session.flush()
            conv = Conversation(account_id=account.id, user_id=user.id)
            session.add(conv)
            session.flush()

            settings = Settings(environment="test")
            res = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-disconnect-1",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id

            run = Run(
                id="run-disconnect-1",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-disconnect-1",
                status="streaming",
            )
            msg_u = ChatMessage(
                id="msg-u-disc",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Tell me a story",
            )
            msg_a = ChatMessage(
                id="msg-a-disc",
                conversation_id=conv.id,
                account_id=account.id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
            )
            session.add_all([run, msg_u, msg_a])
            session.commit()

        call = ProviderCall(
            provider="mock",
            model_id="mock-m",
            operation="generate",
            input_tokens=10,
            output_tokens=30,
            cost_micro=0,
            measurement="test",
            rate_version="v1",
        )
        chunks = [
            StreamChunk(text="Part 1 "),
            StreamChunk(text="Part 2 "),
            StreamChunk(text="Part 3 "),
            StreamChunk(text="", finish_reason=FinishReason.STOP.value, call=call),
        ]
        gateway = DelayableGateway(chunks, delay=0.04)

        run_state = RunState(
            run_id="run-disconnect-1",
            conversation_id=conv.id,
            user_message_id="msg-u-disc",
            assistant_message_id="msg-a-disc",
        )

        runner_task = start_stream_run(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Tell me a story",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res_id,
        )

        # Simulate client consuming first event and then disconnecting (cancelling consumer)
        received_by_client: list[str] = []

        async def _client_consumer():
            async for sse_event in stream_run_events(run_state):
                received_by_client.append(sse_event)
                # Client disconnects as soon as first delta is received
                if "Part 1" in sse_event:
                    break

        consumer_task = asyncio.create_task(_client_consumer())
        await consumer_task

        # Ensure consumer exited / stopped listening
        assert len(received_by_client) >= 1
        assert any("Part 1" in e for e in received_by_client)

        # Crucial assertion: the background runner task is NOT cancelled by client disconnect
        assert not runner_task.cancelled()
        assert not runner_task.done()

        # Wait for the runner to complete its full generation
        await runner_task

        # Verify runner continued all the way to terminal
        assert run_state.terminal is True
        assert run_state.finish_reason == FinishReason.STOP.value
        assert run_state.partial_text == "Part 1 Part 2 Part 3 "

        # Verify DB was updated with final terminal status and full persisted content
        with factory() as session:
            db_run = session.scalar(select(Run).where(Run.id == "run-disconnect-1"))
            assert db_run is not None
            assert db_run.status == RunStatus.COMPLETED
            assert db_run.response_text == "Part 1 Part 2 Part 3 "

            db_msg = session.scalar(select(ChatMessage).where(ChatMessage.id == "msg-a-disc"))
            assert db_msg is not None
            assert db_msg.status == MessageStatus.COMPLETE.value
            assert db_msg.content == "Part 1 Part 2 Part 3 "
            assert db_msg.finish_reason == FinishReason.STOP.value

    asyncio.run(_test())


def test_delta_buffer_eviction_after_10_minutes_emits_resume_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Buffer evicted after 10-minute retention causes GET /v1/runs/{id}/events?after_seq=N

    to emit run.error with category=resume_unavailable and retryable=False.
    """
    registry = get_stream_registry()
    registry.clear()

    client, factory, settings, account, user, token = _setup_test_env(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}

    with factory() as session:
        conv = Conversation(account_id=account.id, user_id=user.id, title="Eviction Test")
        session.add(conv)
        session.flush()

        run = Run(
            id="run-evict-qa-1",
            account_id=account.id,
            user_id=user.id,
            logical_request_id="req-evict-qa-1",
            status="completed",
        )
        msg_u = ChatMessage(
            id="msg-u-evict",
            conversation_id=conv.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Hello",
            run_id=run.id,
        )
        msg_a = ChatMessage(
            id="msg-a-evict",
            conversation_id=conv.id,
            account_id=account.id,
            role="assistant",
            status=MessageStatus.COMPLETE.value,
            content="Hi there!",
            run_id=run.id,
            finish_reason=FinishReason.STOP.value,
        )
        session.add_all([run, msg_u, msg_a])
        session.commit()

    run_state = RunState(
        run_id="run-evict-qa-1",
        conversation_id=conv.id,
        user_message_id="msg-u-evict",
        assistant_message_id="msg-a-evict",
    )

    t0 = 1_000_000.0
    current_time = t0
    monkeypatch.setattr(daily_agent.streaming.registry.time, "time", lambda: current_time)

    async def _populate() -> None:
        await run_state.publish("run.started", {"seq": 0}, seq=0)
        await run_state.publish("message.delta", {"text": "Hi "}, seq=1)
        await run_state.publish("message.delta", {"text": "there!"}, seq=2)
        await run_state.publish("run.finished", {"finish_reason": "stop", "outcome": "COMPLETED"})

    asyncio.run(_populate())
    run_state.terminated_at = t0
    registry.register(run_state)

    # 1. At t0 + 300s (5 minutes in, within 10-minute window): run is still retained in buffer
    current_time = t0 + 300.0
    assert registry.has("run-evict-qa-1")

    # Request after_seq=1 returns delta seq 2 and run.finished
    resp_retained = client.get(
        "/v1/runs/run-evict-qa-1/events?after_seq=1",
        headers=headers,
    )
    assert resp_retained.status_code == 200
    events_retained = _parse_sse(resp_retained.text)
    event_names = [e["event"] for e in events_retained]
    assert "message.delta" in event_names
    assert "run.finished" in event_names
    assert not any(e["event"] == "run.error" for e in events_retained)

    # 2. At t0 + 601s (> 10 minutes retention = 600s): buffer is evicted
    current_time = t0 + 601.0
    assert not registry.has("run-evict-qa-1")

    # Now GET /v1/runs/{id}/events?after_seq=1 emits run.error category=resume_unavailable
    resp_evicted = client.get(
        "/v1/runs/run-evict-qa-1/events?after_seq=1",
        headers=headers,
    )
    assert resp_evicted.status_code == 200
    events_evicted = _parse_sse(resp_evicted.text)
    assert len(events_evicted) == 1
    assert events_evicted[0]["event"] == "run.error"
    data = events_evicted[0]["data"]
    assert data["category"] == "resume_unavailable"
    assert data["retryable"] is False
    assert data["assistant_message_id"] == "msg-a-evict"


def test_budget_settlement_call_count_exactly_once_on_normal_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Budget reserved once and settled exactly once on normal stream completion.

    Assert settlement call count == 1.
    """
    async def _test() -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            account = Account(name="BudgetAcc1")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="BudgetUser1")
            session.add(user)
            session.flush()
            conv = Conversation(account_id=account.id, user_id=user.id)
            session.add(conv)
            session.flush()

            settings = Settings(environment="test")
            res = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-b1",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id

            run = Run(
                id="run-b1",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-b1",
                status="streaming",
            )
            msg_u = ChatMessage(
                id="msg-u-b1",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Ping",
            )
            msg_a = ChatMessage(
                id="msg-a-b1",
                conversation_id=conv.id,
                account_id=account.id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
            )
            session.add_all([run, msg_u, msg_a])
            session.commit()

        real_settle = daily_agent.streaming.runner.settle_budget
        settle_calls: list[dict[str, Any]] = []

        def spy_settle(session: Session, reservation: BudgetReservation, **kwargs: Any) -> Any:
            settle_calls.append({"reservation_id": reservation.id, "kwargs": kwargs})
            return real_settle(session, reservation, **kwargs)

        monkeypatch.setattr(daily_agent.streaming.runner, "settle_budget", spy_settle)

        call = ProviderCall(
            provider="mock",
            model_id="mock-m",
            operation="generate",
            input_tokens=5,
            output_tokens=10,
            cost_micro=100,
            measurement="test",
            rate_version="v1",
        )
        chunks = [
            StreamChunk(text="Pong "),
            StreamChunk(text="", finish_reason=FinishReason.STOP.value, call=call),
        ]
        gateway = DelayableGateway(chunks)

        run_state = RunState(
            run_id="run-b1",
            conversation_id=conv.id,
            user_message_id="msg-u-b1",
            assistant_message_id="msg-a-b1",
        )
        runner = StreamRunner(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Ping",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res_id,
        )

        await runner.run()

        # Assert settle_budget was called exactly once
        assert len(settle_calls) == 1
        assert settle_calls[0]["reservation_id"] == res_id

        # Verify DB reservation is SETTLED
        with factory() as session:
            db_res = session.get(BudgetReservation, res_id)
            assert db_res is not None
            assert db_res.status == ReservationStatus.SETTLED

        # Verify idempotence: subsequent calls to _settle_or_release_budget must not settle again
        runner._settle_or_release_budget(release=False)
        assert len(settle_calls) == 1

    asyncio.run(_test())


def test_budget_settlement_call_count_exactly_once_on_stop_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Budget settled exactly once when run is stopped/cancelled mid-stream.

    Assert settlement call count == 1.
    """
    async def _test() -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            account = Account(name="BudgetAcc2")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="BudgetUser2")
            session.add(user)
            session.flush()
            conv = Conversation(account_id=account.id, user_id=user.id)
            session.add(conv)
            session.flush()

            settings = Settings(environment="test")
            res = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-b2",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id

            run = Run(
                id="run-b2",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-b2",
                status="streaming",
            )
            msg_u = ChatMessage(
                id="msg-u-b2",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Long task",
            )
            msg_a = ChatMessage(
                id="msg-a-b2",
                conversation_id=conv.id,
                account_id=account.id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
            )
            session.add_all([run, msg_u, msg_a])
            session.commit()

        real_settle = daily_agent.streaming.runner.settle_budget
        settle_calls: list[dict[str, Any]] = []

        def spy_settle(session: Session, reservation: BudgetReservation, **kwargs: Any) -> Any:
            settle_calls.append({"reservation_id": reservation.id, "kwargs": kwargs})
            return real_settle(session, reservation, **kwargs)

        monkeypatch.setattr(daily_agent.streaming.runner, "settle_budget", spy_settle)

        chunks = [
            StreamChunk(text="Chunk 1 "),
            StreamChunk(text="Chunk 2 "),
            StreamChunk(text="Chunk 3 "),
        ]
        gateway = DelayableGateway(chunks, delay=0.05)

        run_state = RunState(
            run_id="run-b2",
            conversation_id=conv.id,
            user_message_id="msg-u-b2",
            assistant_message_id="msg-a-b2",
        )

        runner_task = start_stream_run(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Long task",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res_id,
        )

        # Allow at least one chunk to be processed
        await asyncio.sleep(0.06)

        # Cancel/stop the run mid-stream
        run_state.stop()

        with pytest.raises(asyncio.CancelledError):
            await runner_task

        # Assert settle_budget was called exactly once despite cancellation
        assert len(settle_calls) == 1
        assert settle_calls[0]["reservation_id"] == res_id

        # Verify DB reservation is SETTLED
        with factory() as session:
            db_res = session.get(BudgetReservation, res_id)
            assert db_res is not None
            assert db_res.status == ReservationStatus.SETTLED

            db_run = session.get(Run, "run-b2")
            assert db_run is not None
            assert db_run.finish_reason == FinishReason.CANCELLED.value

    asyncio.run(_test())


def test_budget_settlement_call_count_exactly_once_on_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Budget settled exactly once when generation crashes after partial deltas.

    If error occurs after deltas, settle_budget is called once.
    If error occurs before any deltas, release_budget is called once.
    """
    async def _test() -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        # Case 1: Error with partial text -> settle_budget called exactly once
        with factory() as session:
            account = Account(name="BudgetAcc3")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="BudgetUser3")
            session.add(user)
            session.flush()
            conv = Conversation(account_id=account.id, user_id=user.id)
            session.add(conv)
            session.flush()

            settings = Settings(environment="test")
            res1 = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-b3",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res1_id = res1.id

            run1 = Run(
                id="run-b3",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-b3",
                status="streaming",
            )
            msg_u1 = ChatMessage(
                id="msg-u-b3",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Fail later",
            )
            msg_a1 = ChatMessage(
                id="msg-a-b3",
                conversation_id=conv.id,
                account_id=account.id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
            )
            session.add_all([run1, msg_u1, msg_a1])
            session.commit()

        real_settle = daily_agent.streaming.runner.settle_budget
        settle_calls: list[dict[str, Any]] = []

        def spy_settle(session: Session, reservation: BudgetReservation, **kwargs: Any) -> Any:
            settle_calls.append({"reservation_id": reservation.id, "kwargs": kwargs})
            return real_settle(session, reservation, **kwargs)

        monkeypatch.setattr(daily_agent.streaming.runner, "settle_budget", spy_settle)

        # Gateway emits one chunk, then crashes
        chunks = [
            StreamChunk(text="Some partial content"),
            StreamChunk(text="Never reached"),
        ]
        gateway1 = DelayableGateway(chunks, fail_after_chunks=1)

        run_state1 = RunState(
            run_id="run-b3",
            conversation_id=conv.id,
            user_message_id="msg-u-b3",
            assistant_message_id="msg-a-b3",
        )
        runner1 = StreamRunner(
            run_state=run_state1,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Fail later",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway1,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res1_id,
        )

        await runner1.run()

        # Assert settle_budget was called exactly once
        assert len(settle_calls) == 1
        assert settle_calls[0]["reservation_id"] == res1_id

        with factory() as session:
            db_res1 = session.get(BudgetReservation, res1_id)
            assert db_res1 is not None
            assert db_res1.status == ReservationStatus.SETTLED

        # Case 2: Error before any text -> release_budget called exactly once
        with factory() as session:
            res2 = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-b4",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res2_id = res2.id

            run2 = Run(
                id="run-b4",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-b4",
                status="streaming",
            )
            msg_u2 = ChatMessage(
                id="msg-u-b4",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Fail immediately",
            )
            msg_a2 = ChatMessage(
                id="msg-a-b4",
                conversation_id=conv.id,
                account_id=account.id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
            )
            session.add_all([run2, msg_u2, msg_a2])
            session.commit()

        real_release = daily_agent.streaming.runner.release_budget
        release_calls: list[dict[str, Any]] = []

        def spy_release(session: Session, reservation: BudgetReservation, **kwargs: Any) -> Any:
            release_calls.append({"reservation_id": reservation.id, "kwargs": kwargs})
            return real_release(session, reservation, **kwargs)

        monkeypatch.setattr(daily_agent.streaming.runner, "release_budget", spy_release)

        gateway2 = DelayableGateway(chunks, fail_after_chunks=0)
        run_state2 = RunState(
            run_id="run-b4",
            conversation_id=conv.id,
            user_message_id="msg-u-b4",
            assistant_message_id="msg-a-b4",
        )
        runner2 = StreamRunner(
            run_state=run_state2,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Fail immediately",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway2,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res2_id,
        )

        await runner2.run()

        # Release called once, settle called 0 additional times
        assert len(release_calls) == 1
        assert release_calls[0]["reservation_id"] == res2_id
        assert len(settle_calls) == 1  # unchanged from case 1

        with factory() as session:
            db_res2 = session.get(BudgetReservation, res2_id)
            assert db_res2 is not None
            assert db_res2.status == ReservationStatus.RELEASED

    asyncio.run(_test())


# ============================================================================
# (b) Conversations search tests
# ============================================================================


def test_search_like_escaping_percent_underscore_and_backslash(tmp_path: Path) -> None:
    """LIKE wildcards %, _, and backslash are escaped.

    Searching for '%', '_', or '\\' must not match everything, only exact literal occurrences.
    Tested both at service level and API route level.
    """
    client, factory, settings, account, user, token = _setup_test_env(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    principal = Principal(user_id=user.id, account_id=account.id, role=user.role)

    with factory() as session:
        # Conversation with normal text (no wildcards)
        conv_plain = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Normal Conversation Title",
            updated_at=utcnow(),
        )
        msg_plain = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv_plain.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Regular conversation content without wildcards",
        )

        # Conversation with literal '%'
        conv_percent = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="100% Guaranteed Success",
            updated_at=utcnow(),
        )
        msg_percent = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv_percent.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Get 50% discount on subscription",
        )

        # Conversation with literal '_'
        conv_underscore = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="snake_case_identifier_name",
            updated_at=utcnow(),
        )
        msg_underscore = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv_underscore.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Check variable user_profile_id",
        )

        # Conversation with literal '\'
        conv_backslash = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title=r"Path C:\Users\Admin",
            updated_at=utcnow(),
        )
        msg_backslash = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv_backslash.id,
            account_id=account.id,
            role="user",
            status="complete",
            content=r"Saved at D:\data\logs",
        )

        session.add_all([
            conv_plain, msg_plain,
            conv_percent, msg_percent,
            conv_underscore, msg_underscore,
            conv_backslash, msg_backslash,
        ])
        session.commit()

        # 1. Service-level checks
        # Query '%' must match ONLY conv_percent
        res_percent = search_conversations(session, principal, "%")
        percent_ids = [r.conversation.id for r in res_percent]
        assert percent_ids == [conv_percent.id]
        assert conv_plain.id not in percent_ids
        assert conv_underscore.id not in percent_ids
        assert conv_backslash.id not in percent_ids

        # Query '_' must match ONLY conv_underscore
        res_underscore = search_conversations(session, principal, "_")
        underscore_ids = [r.conversation.id for r in res_underscore]
        assert underscore_ids == [conv_underscore.id]
        assert conv_plain.id not in underscore_ids
        assert conv_percent.id not in underscore_ids
        assert conv_backslash.id not in underscore_ids

        # Query '\\' must match ONLY conv_backslash
        res_backslash = search_conversations(session, principal, "\\")
        backslash_ids = [r.conversation.id for r in res_backslash]
        assert backslash_ids == [conv_backslash.id]
        assert conv_plain.id not in backslash_ids
        assert conv_percent.id not in backslash_ids
        assert conv_underscore.id not in backslash_ids

    # 2. HTTP API route checks
    # Route: GET /v1/conversations/search?q=%
    resp_percent = client.get("/v1/conversations/search?q=%25", headers=headers)
    assert resp_percent.status_code == 200
    data_percent = resp_percent.json()
    assert len(data_percent) == 1
    assert data_percent[0]["conversation"]["id"] == conv_percent.id

    # Route: GET /v1/conversations/search?q=_
    resp_underscore = client.get("/v1/conversations/search?q=_", headers=headers)
    assert resp_underscore.status_code == 200
    data_underscore = resp_underscore.json()
    assert len(data_underscore) == 1
    assert data_underscore[0]["conversation"]["id"] == conv_underscore.id

    # Route: GET /v1/conversations/search?q=\
    resp_backslash = client.get("/v1/conversations/search?q=%5C", headers=headers)
    assert resp_backslash.status_code == 200
    data_backslash = resp_backslash.json()
    assert len(data_backslash) == 1
    assert data_backslash[0]["conversation"]["id"] == conv_backslash.id


def test_search_pagination_and_limit_bounds(tmp_path: Path) -> None:
    """Search pagination respects limit parameter, enforces limit<=50, and is stably ordered."""
    client, factory, settings, account, user, token = _setup_test_env(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    base_time = utcnow()

    with factory() as session:
        # Seed 60 conversations with a common search keyword
        convs = []
        for i in range(60):
            c = Conversation(
                id=f"conv_search_p_{i:03d}",
                account_id=account.id,
                user_id=user.id,
                title=f"TargetSearch Keyword Conversation {i:03d}",
                updated_at=base_time + timedelta(seconds=i),
                created_at=base_time + timedelta(seconds=i),
            )
            convs.append(c)
        session.add_all(convs)
        session.commit()

    # 1. Search with limit=5 returns exactly 5 items
    resp5 = client.get("/v1/conversations/search?q=TargetSearch&limit=5", headers=headers)
    assert resp5.status_code == 200
    data5 = resp5.json()
    assert len(data5) == 5

    # 2. Check stability of ordering: updated_at DESC, id DESC
    # Newest (i=59, 58, 57, 56, 55) should be returned first
    returned_ids = [item["conversation"]["id"] for item in data5]
    expected_top5 = [f"conv_search_p_{i:03d}" for i in range(59, 54, -1)]
    assert returned_ids == expected_top5

    # 3. Search with limit=50 returns maximum allowed 50 items
    resp50 = client.get("/v1/conversations/search?q=TargetSearch&limit=50", headers=headers)
    assert resp50.status_code == 200
    assert len(resp50.json()) == 50

    # 4. Search with limit > 50 must be rejected with 422 Unprocessable Entity
    resp51 = client.get("/v1/conversations/search?q=TargetSearch&limit=51", headers=headers)
    assert resp51.status_code == 422

    # 5. Search with limit < 1 must be rejected with 422
    resp0 = client.get("/v1/conversations/search?q=TargetSearch&limit=0", headers=headers)
    assert resp0.status_code == 422


def test_conversations_list_cursor_pagination_and_limit_bounds(tmp_path: Path) -> None:
    """Conversation listing cursor pagination is stable and enforces limit<=50."""
    client, factory, settings, account, user, token = _setup_test_env(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
    base_time = utcnow()

    with factory() as session:
        # Create 10 conversations
        convs = []
        for i in range(10):
            c = Conversation(
                id=f"conv_list_p_{i:02d}",
                account_id=account.id,
                user_id=user.id,
                title=f"List Item {i:02d}",
                pinned=(i == 9),  # i=9 is pinned
                updated_at=base_time + timedelta(seconds=i),
                created_at=base_time + timedelta(seconds=i),
            )
            convs.append(c)
        session.add_all(convs)
        session.commit()

        # Service-level pagination with cursor: page 1 (limit 3)
        p1_items, next_cursor = list_conversations(session, principal, limit=3)
        assert len(p1_items) == 3
        assert next_cursor is not None

        # Page 2 (limit 3) with next_cursor
        p2_items, next_cursor2 = list_conversations(session, principal, cursor=next_cursor, limit=3)
        assert len(p2_items) == 3
        assert next_cursor2 is not None

        # Verify no overlap between page 1 and page 2
        p1_ids = {c.id for c in p1_items}
        p2_ids = {c.id for c in p2_items}
        assert p1_ids.isdisjoint(p2_ids)

    # HTTP route level: limit > 50 returns 422
    resp_over = client.get("/v1/conversations?limit=51", headers=headers)
    assert resp_over.status_code == 422

    # HTTP route level: invalid cursor returns 422
    resp_bad_cursor = client.get("/v1/conversations?cursor=invalid_bad_cursor", headers=headers)
    assert resp_bad_cursor.status_code == 422


def test_cross_user_search_isolation(tmp_path: Path) -> None:
    """Cross-user search returns no rows of other users.

    Ensures neither users in another account nor other users in the same account can see results.
    """
    client, factory, settings, account_a, user_a, token_a = _setup_test_env(tmp_path)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    with factory() as session:
        # User B in a different account
        account_b, user_b, token_b = create_identity(session, settings, name="UserB")

        # User C in the same account as User A
        user_c = User(account_id=account_a.id, display_name="UserC", role="customer")
        session.add(user_c)
        session.flush()
        from daily_agent.security import issue_development_token
        token_c = issue_development_token(user_c, settings)

        # User A's private conversation and message with unique secret keywords
        secret_keyword = "classified_mars_mission_payload_alpha"  # noqa: S105 - test search term, not password
        conv_a = Conversation(
            id=f"conv_a_{uuid4().hex}",
            account_id=account_a.id,
            user_id=user_a.id,
            title=f"Top Secret {secret_keyword}",
            updated_at=utcnow(),
        )
        msg_a = ChatMessage(
            id=f"msg_a_{uuid4().hex}",
            conversation_id=conv_a.id,
            account_id=account_a.id,
            role="user",
            status="complete",
            content=f"Secret details regarding {secret_keyword}",
        )
        session.add_all([conv_a, msg_a])
        session.commit()

        principal_b = Principal(user_id=user_b.id, account_id=account_b.id, role=user_b.role)
        principal_c = Principal(user_id=user_c.id, account_id=account_a.id, role=user_c.role)

        # Service-level assertions
        results_b = search_conversations(session, principal_b, secret_keyword)
        assert len(results_b) == 0

        results_c = search_conversations(session, principal_c, secret_keyword)
        assert len(results_c) == 0

    # API-level assertions
    # 1. User B (different account) searches
    resp_b = client.get(
        f"/v1/conversations/search?q={secret_keyword}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 200
    assert resp_b.json() == []

    # 2. User C (same account, different user) searches
    resp_c = client.get(
        f"/v1/conversations/search?q={secret_keyword}",
        headers={"Authorization": f"Bearer {token_c}"},
    )
    assert resp_c.status_code == 200
    assert resp_c.json() == []

    # 3. User A searches and finds their conversation
    resp_a = client.get(
        f"/v1/conversations/search?q={secret_keyword}",
        headers=headers_a,
    )
    assert resp_a.status_code == 200
    results_a = resp_a.json()
    assert len(results_a) == 1
    assert results_a[0]["conversation"]["id"] == conv_a.id
