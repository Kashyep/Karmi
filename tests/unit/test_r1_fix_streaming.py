"""Targeted regression tests for R1 fixes:
- #3: Startup sweep releases RESERVED budget reservations idempotently
- #4: StreamRegistry evicts on register() and finalizes+evicts stuck non-terminal runs
- #5: StreamRunner flushes off the event loop thread
- #10: Unused gateway admission slots refunded on terminal
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import threading
import time
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from daily_agent.config import Settings
from daily_agent.db import Base
from daily_agent.gateway.types import StreamChunk, TaskType
from daily_agent.models import (
    Account,
    BudgetReservation,
    ChatMessage,
    Conversation,
    GatewayRequestDay,
    PlatformBudget,
    ReservationStatus,
    Run,
    UsageWindow,
    User,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.providers import ProviderCall
from daily_agent.schemas_chat import FinishReason, MessageStatus
from daily_agent.services import (
    admit_gateway_requests,
    current_window_key,
    reserve_budget,
)
from daily_agent.streaming.registry import (
    RunState,
    StreamRegistry,
    sweep_interrupted_runs,
)
from daily_agent.streaming.runner import StreamRunner


class FakeGateway:
    def __init__(self, chunks: list[StreamChunk]) -> None:
        self.chunks = chunks

    async def stream(self, **kwargs: Any):
        for chunk in self.chunks:
            yield chunk


def test_sweep_releases_reserved_reservation_and_is_idempotent() -> None:
    """Finding #3:
    - sweep releases a RESERVED reservation (UsageWindow/PlatformBudget reserved values return to prior)
    - second sweep does not double-release.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    settings = Settings(environment="test")
    with factory() as session:
        account = Account(name="TestAccount")
        session.add(account)
        session.flush()

        user = User(account_id=account.id, display_name="TestUser")
        session.add(user)
        session.flush()

        conv = Conversation(account_id=account.id, user_id=user.id)
        session.add(conv)
        session.flush()

        # Reserve budget
        res = reserve_budget(
            session,
            settings=settings,
            account_id=account.id,
            logical_request_id="logical-req-1",
            stage="execution",
            amount_micro=1000,
            tokens=100,
        )
        session.flush()
        res_id = res.id

        window = session.get(UsageWindow, res.usage_window_id)
        assert window is not None
        window_reserved_before = window.reserved_micro
        window_tokens_before = window.tokens_reserved

        pbudget = session.scalar(select(PlatformBudget).where(PlatformBudget.window_key == window.window_key))
        assert pbudget is not None
        pbudget_reserved_before = pbudget.reserved_micro

        # Run left in streaming state
        run = Run(
            id="run-sweep-1",
            account_id=account.id,
            user_id=user.id,
            logical_request_id="logical-req-1",
            status="streaming",
        )
        msg = ChatMessage(
            id="msg-sweep-1",
            conversation_id=conv.id,
            account_id=account.id,
            role="assistant",
            status=MessageStatus.STREAMING.value,
        )
        session.add_all([run, msg])
        session.commit()

    # First sweep
    with factory() as session:
        count = sweep_interrupted_runs(session)
        assert count == 1

        db_run = session.scalar(select(Run).where(Run.id == "run-sweep-1"))
        assert db_run is not None
        assert db_run.status == "interrupted"

        db_res = session.get(BudgetReservation, res_id)
        assert db_res is not None
        assert db_res.status == ReservationStatus.RELEASED

        db_window = session.get(UsageWindow, db_res.usage_window_id)
        assert db_window is not None
        assert db_window.reserved_micro == window_reserved_before - 1000
        assert db_window.tokens_reserved == window_tokens_before - 100

        db_pbudget = session.scalar(select(PlatformBudget).where(PlatformBudget.window_key == db_window.window_key))
        assert db_pbudget is not None
        assert db_pbudget.reserved_micro == pbudget_reserved_before - 1000

    # Second sweep: idempotent, does not double-release
    with factory() as session:
        count2 = sweep_interrupted_runs(session)
        assert count2 == 0

        db_res2 = session.get(BudgetReservation, res_id)
        assert db_res2 is not None
        assert db_res2.status == ReservationStatus.RELEASED

        db_window2 = session.get(UsageWindow, db_res2.usage_window_id)
        assert db_window2 is not None
        assert db_window2.reserved_micro == window_reserved_before - 1000
        assert db_window2.tokens_reserved == window_tokens_before - 100


def test_registry_register_evicts_terminal_run_without_get() -> None:
    """Finding #4:
    register() evicts a terminal run past retention without any get() call.
    """
    registry = StreamRegistry()
    now = time.time()

    # Old terminal run: terminated 700 seconds ago (retention is 600s)
    old_run = RunState("r_old", "c1", "u1", "a1", terminal=True, terminated_at=now - 700.0)
    registry._runs["r_old"] = old_run
    assert "r_old" in registry._runs

    # Registering a new run triggers eviction without calling get() or has()
    new_run = RunState("r_new", "c1", "u1", "a2")
    registry.register(new_run)

    # r_old must be evicted directly from internal dictionary
    assert "r_old" not in registry._runs
    assert "r_new" in registry._runs


def test_registry_evicts_and_finalizes_stuck_non_terminal_run() -> None:
    """Finding #4:
    A non-terminal run older than stuck_timeout is finalized (terminal event emitted,
    budget settled exactly once) and evicted.
    """
    registry = StreamRegistry(stuck_timeout_seconds=60.0)
    now = time.time()

    settle_count = 0

    def mock_finalize():
        nonlocal settle_count
        settle_count += 1

    stuck_run = RunState(
        run_id="r_stuck",
        conversation_id="c1",
        user_message_id="u1",
        assistant_message_id="a1",
        created_at=now - 100.0,
        on_finalize=mock_finalize,
    )
    registry._runs["r_stuck"] = stuck_run

    evicted = registry.evict_expired(now=now)
    assert evicted == 1
    assert "r_stuck" not in registry._runs

    # Verify run was finalized
    assert stuck_run.terminal is True
    assert settle_count == 1
    assert any(evt.event == "run.error" for evt in stuck_run.events)


def test_stream_runner_flush_runs_off_loop_thread() -> None:
    """Finding #5:
    StreamRunner's synchronous DB flush runs off the main event loop thread.
    Assert threading.get_ident() != main loop thread id inside flush.
    """
    async def _test() -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        settings = Settings(environment="test")
        with factory() as session:
            account = Account(name="TestAcc")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="TestUser")
            session.add(user)
            session.flush()
            conv = Conversation(account_id=account.id, user_id=user.id)
            session.add(conv)
            session.flush()
            res = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-flush-test",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id
            run = Run(
                id="run-flush-1",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-flush-test",
                status="streaming",
            )
            msg_u = ChatMessage(
                id="msg-u1",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Hello",
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

        loop_thread_id = threading.get_ident()
        flush_thread_ids: list[int] = []

        call = ProviderCall(
            provider="mock",
            model_id="mock-m",
            operation="generate",
            input_tokens=5,
            output_tokens=5,
            cost_micro=0,
            measurement="test",
            rate_version="v1",
        )
        chunks = [
            StreamChunk(text="Delta 1"),
            StreamChunk(text="", finish_reason=FinishReason.STOP.value, call=call),
        ]
        gateway = FakeGateway(chunks)
        run_state = RunState(
            run_id="run-flush-1",
            conversation_id=conv.id,
            user_message_id="msg-u1",
            assistant_message_id="msg-a1",
        )
        runner = StreamRunner(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Hello",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=settings,
            session_factory=factory,
            reservation_id=res_id,
        )

        orig_flush = runner._flush_db

        def spy_flush(*args: Any, **kwargs: Any) -> Any:
            flush_thread_ids.append(threading.get_ident())
            return orig_flush(*args, **kwargs)

        runner._flush_db = spy_flush

        await runner.run()

        assert len(flush_thread_ids) > 0
        # Assert each flush executed off the main event loop thread
        for tid in flush_thread_ids:
            assert tid != loop_thread_id

    asyncio.run(_test())


def test_gateway_admission_refunds_unused_slots_on_terminal() -> None:
    """Finding #10:
    Admission slots refunded on terminal: GatewayRequestDay.requests_used reflects used=1 not 2.
    """
    async def _test() -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        settings = Settings(environment="test")
        now = datetime.now(UTC)
        day_key, _ = current_window_key(now)

        with factory() as session:
            account = Account(name="TestAcc")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="TestUser")
            session.add(user)
            session.flush()
            conv = Conversation(account_id=account.id, user_id=user.id)
            session.add(conv)
            session.flush()

            # Admit 2 slots
            admission = admit_gateway_requests(session, settings, paid=True, slots=2, now=now)
            session.flush()

            # Verify initial used slots = 2
            day_row = session.get(GatewayRequestDay, day_key)
            assert day_row is not None
            assert day_row.requests_used == 2

            res = reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="req-admission-test",
                stage="execution",
                amount_micro=1000,
                tokens=100,
            )
            session.flush()
            res_id = res.id

            run = Run(
                id="run-adm-1",
                account_id=account.id,
                user_id=user.id,
                logical_request_id="req-admission-test",
                status="streaming",
            )
            msg_u = ChatMessage(
                id="msg-u-adm",
                conversation_id=conv.id,
                account_id=account.id,
                role="user",
                status="complete",
                content="Hello",
            )
            msg_a = ChatMessage(
                id="msg-a-adm",
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
            input_tokens=5,
            output_tokens=5,
            cost_micro=0,
            measurement="test",
            rate_version="v1",
        )
        chunks = [
            StreamChunk(text="Response"),
            StreamChunk(text="", finish_reason=FinishReason.STOP.value, call=call),
        ]
        gateway = FakeGateway(chunks)
        run_state = RunState(
            run_id="run-adm-1",
            conversation_id=conv.id,
            user_message_id="msg-u-adm",
            assistant_message_id="msg-a-adm",
        )
        runner = StreamRunner(
            run_state=run_state,
            plan=SYNTHETIC_POLICIES["ananta"],
            text="Hello",
            task_type=TaskType.STUDY,
            max_output_tokens=100,
            gateway=gateway,  # type: ignore[arg-type]
            settings=settings,
            session_factory=factory,
            reservation_id=res_id,
            admission=admission,
        )

        await runner.run()

        # On terminal, unused slot (2 - 1 = 1) was returned
        with factory() as session:
            day_row = session.get(GatewayRequestDay, day_key)
            assert day_row is not None
            assert day_row.requests_used == 1

    asyncio.run(_test())
