import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from daily_agent.db import Base
from daily_agent.models import Account, ChatMessage, Conversation, Run, User
from daily_agent.schemas_chat import FinishReason, MessageStatus
from daily_agent.streaming.registry import RunState, StreamRegistry, sweep_interrupted_runs


def test_run_state_publish_seq_and_terminal() -> None:
    async def _test() -> None:
        state = RunState(
            run_id="run_1",
            conversation_id="conv_1",
            user_message_id="msg_u1",
            assistant_message_id="msg_a1",
        )
        assert state.last_seq == 0
        assert not state.terminal

        await state.publish("run.started", {"seq": 0}, seq=0)
        assert state.last_seq == 0
        assert len(state.events) == 1

        await state.publish("message.delta", {"text": "Hello "}, seq=1)
        assert state.last_seq == 1
        assert state.partial_text == "Hello "

        await state.publish("message.delta", {"text": "world!"}, seq=2)
        assert state.last_seq == 2
        assert state.partial_text == "Hello world!"

        await state.publish("run.finished", {"finish_reason": "stop", "outcome": "COMPLETED"})
        assert state.terminal
        assert state.terminated_at is not None
        assert state.finish_reason == "stop"

    asyncio.run(_test())


def test_registry_eviction() -> None:
    import time
    registry = StreamRegistry()
    now = time.time()
    state_active = RunState("r_active", "c1", "u1", "a1")
    state_recent = RunState("r_recent", "c1", "u1", "a2", terminal=True, terminated_at=now - 50.0)
    state_old = RunState("r_old", "c1", "u1", "a3", terminal=True, terminated_at=now - 700.0)

    registry.register(state_active)
    registry.register(state_recent)
    registry.register(state_old)

    evicted = registry.evict_expired(ttl_seconds=600.0, now=now)
    assert evicted == 1
    assert registry.has("r_active")
    assert registry.has("r_recent")
    assert not registry.has("r_old")


def test_sweep_interrupted_runs() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        account = Account(name="Test")
        session.add(account)
        session.flush()
        user = User(account_id=account.id, display_name="Test")
        session.add(user)
        session.flush()
        conv = Conversation(account_id=account.id, user_id=user.id)
        session.add(conv)
        session.flush()

        run_streaming = Run(
            id="r1",
            account_id=account.id,
            user_id=user.id,
            logical_request_id="l1",
            status="streaming",
        )
        run_completed = Run(
            id="r2",
            account_id=account.id,
            user_id=user.id,
            logical_request_id="l2",
            status="completed",
        )
        msg_streaming = ChatMessage(
            id="m1",
            conversation_id=conv.id,
            account_id=account.id,
            role="assistant",
            status=MessageStatus.STREAMING.value,
        )
        msg_complete = ChatMessage(
            id="m2",
            conversation_id=conv.id,
            account_id=account.id,
            role="assistant",
            status=MessageStatus.COMPLETE.value,
        )
        session.add_all([run_streaming, run_completed, msg_streaming, msg_complete])
        session.commit()

        count = sweep_interrupted_runs(session)
        assert count == 1

        r1 = session.scalar(select(Run).where(Run.id == "r1"))
        assert r1 is not None
        assert r1.status == "interrupted"
        assert r1.finish_reason == FinishReason.INTERRUPTED.value

        r2 = session.scalar(select(Run).where(Run.id == "r2"))
        assert r2 is not None
        assert r2.status == "completed"

        m1 = session.scalar(select(ChatMessage).where(ChatMessage.id == "m1"))
        assert m1 is not None
        assert m1.status == MessageStatus.INTERRUPTED.value
        assert m1.finish_reason == FinishReason.INTERRUPTED.value
