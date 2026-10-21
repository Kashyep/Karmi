import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from daily_agent.config import Settings
from daily_agent.db import Base
from daily_agent.gateway.types import StreamChunk, TaskType
from daily_agent.models import (
    Account,
    BudgetReservation,
    ChatMessage,
    Conversation,
    ReservationStatus,
    Run,
    User,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.providers import ProviderCall
from daily_agent.schemas_chat import FinishReason, MessageStatus
from daily_agent.services import reserve_budget
from daily_agent.streaming.registry import RunState
from daily_agent.streaming.runner import StreamRunner


class FakeGateway:
    def __init__(self, chunks: list[StreamChunk], delay: float = 0.0) -> None:
        self.chunks = chunks
        self.delay = delay

    async def stream(self, **kwargs: object) -> AsyncIterator[StreamChunk]:
        for chunk in self.chunks:
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            yield chunk


def test_stream_runner_happy_path_and_budget() -> None:
    async def _test() -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            account = Account(name="TestAcc")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="User")
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
                logical_request_id="req-1",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id

            run = Run(
                id="run-1",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-1",
                status="streaming",
            )
            msg_u = ChatMessage(
                id="msg-u1",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Hi",
            )
            msg_a = ChatMessage(
                id="msg-a1",
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
            output_tokens=15,
            cost_micro=0,
            measurement="test",
            rate_version="v1",
        )
        chunks = [
            StreamChunk(text="Hello "),
            StreamChunk(text="there!"),
            StreamChunk(text="", finish_reason=FinishReason.STOP.value, call=call),
        ]
        gateway = FakeGateway(chunks)

        run_state = RunState(
            run_id="run-1",
            conversation_id="conv-1",
            user_message_id="msg-u1",
            assistant_message_id="msg-a1",
        )
        runner = StreamRunner(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Hi",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res_id,
        )

        await runner.run()

        # Check events order: run.started (seq 0) -> message.delta (seq 1) -> message.delta (seq 2) -> run.finished
        events = run_state.events
        assert len(events) == 4
        assert events[0].event == "run.started"
        assert events[0].seq == 0
        assert events[1].event == "message.delta"
        assert events[1].data["text"] == "Hello "
        assert events[1].seq == 1
        assert events[2].event == "message.delta"
        assert events[2].data["text"] == "there!"
        assert events[2].seq == 2
        assert events[3].event == "run.finished"
        assert events[3].data["finish_reason"] == "stop"
        assert events[3].data["outcome"] == "COMPLETED"

        # Verify single terminal
        terminal_events = [e for e in events if e.event in ("run.finished", "run.error")]
        assert len(terminal_events) == 1

        # Verify DB update
        with factory() as session:
            db_run = session.scalar(select(Run).where(Run.id == "run-1"))
            assert db_run is not None
            assert db_run.status == "completed"
            assert db_run.response_text == "Hello there!"
            assert db_run.finish_reason == "stop"

            db_msg = session.scalar(select(ChatMessage).where(ChatMessage.id == "msg-a1"))
            assert db_msg is not None
            assert db_msg.status == MessageStatus.COMPLETE.value
            assert db_msg.content == "Hello there!"
            assert db_msg.finish_reason == "stop"

            # Verify budget settled
            db_res = session.get(BudgetReservation, res_id)
            assert db_res is not None
            assert db_res.status == ReservationStatus.SETTLED

    asyncio.run(_test())


def test_stream_runner_stop_cancelled() -> None:
    async def _test() -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            account = Account(name="TestAcc")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="User")
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
                logical_request_id="req-2",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id

            run = Run(
                id="run-2",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-2",
                status="streaming",
            )
            msg_a = ChatMessage(
                id="msg-a2",
                conversation_id=conv.id,
                account_id=account.id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
            )
            session.add_all([run, msg_a])
            session.commit()

        chunks = [
            StreamChunk(text="Initial part "),
            StreamChunk(text="never arrives"),
        ]
        gateway = FakeGateway(chunks, delay=0.1)

        run_state = RunState(
            run_id="run-2",
            conversation_id="conv-2",
            user_message_id="msg-u2",
            assistant_message_id="msg-a2",
        )
        runner = StreamRunner(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Hi",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=Settings(environment="test"),
            session_factory=factory,
            reservation_id=res_id,
        )

        task = asyncio.create_task(runner.run())
        run_state.task = task
        # Wait for first delta to be emitted
        await asyncio.sleep(0.05)
        run_state.stop()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Check terminal event is cancelled
        events = run_state.events
        assert any(e.event == "run.finished" and e.data["finish_reason"] == "cancelled" for e in events)

        # Check DB state
        with factory() as session:
            db_run = session.scalar(select(Run).where(Run.id == "run-2"))
            assert db_run is not None
            assert db_run.finish_reason == FinishReason.CANCELLED.value
            assert db_run.outcome == "STOPPED"

            db_msg = session.scalar(select(ChatMessage).where(ChatMessage.id == "msg-a2"))
            assert db_msg is not None
            assert db_msg.status == MessageStatus.STOPPED.value
            assert db_msg.finish_reason == FinishReason.CANCELLED.value

    asyncio.run(_test())
