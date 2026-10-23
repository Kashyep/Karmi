from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from daily_agent.conversations.service import search_conversations
from daily_agent.models import (
    BudgetReservation,
    ChatMessage,
    Conversation,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.security import Principal
from daily_agent.services import (
    RESERVATION_LEASE_SECONDS,
    InputTooLarge,
    ensure_input_fits,
    reclaim_stale_reservations,
    reserve_budget,
)
from tests.conftest import create_identity


def _tight_plan(input_tokens: int):  # type: ignore[no-untyped-def]
    return replace(SYNTHETIC_POLICIES["ananta"], input_tokens=input_tokens)


def test_ensure_input_fits_accepts_text_within_budget() -> None:
    plan = _tight_plan(input_tokens=100)
    ensure_input_fits("a" * 400, plan)  # 400 bytes // 4 == 100 tokens


def test_ensure_input_fits_rejects_oversized_text() -> None:
    plan = _tight_plan(input_tokens=100)
    with pytest.raises(InputTooLarge) as excinfo:
        ensure_input_fits("a" * 404, plan)  # 404 // 4 == 101 tokens > 100
    assert excinfo.value.max_input_tokens == 100


def test_ensure_input_fits_counts_utf8_bytes_not_chars() -> None:
    plan = _tight_plan(input_tokens=10)
    # 20 chars of 'é' are 40 UTF-8 bytes -> 10 tokens, exactly at the limit.
    ensure_input_fits("é" * 20, plan)
    with pytest.raises(InputTooLarge):
        ensure_input_fits("é" * 22, plan)  # 44 UTF-8 bytes -> 11 tokens > 10


def test_reserve_path_does_not_sweep_other_stale_holds(
    test_context: dict[str, object],
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="Hot")  # type: ignore[arg-type]
        stale = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="stale",
            stage="execution",
            amount_micro=100,
        )
        stale.created_at = datetime.now(UTC) - timedelta(seconds=RESERVATION_LEASE_SECONDS + 10)
        session.commit()
        reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="fresh",
            stage="execution",
            amount_micro=100,
        )
        session.commit()
        still = session.get(BudgetReservation, stale.id)
        assert still is not None and still.status == "reserved"


def test_reclaim_sweep_covers_all_accounts_and_skips_fresh_holds(
    test_context: dict[str, object],
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    expired_at = datetime.now(UTC) - timedelta(seconds=RESERVATION_LEASE_SECONDS + 10)
    with factory() as session:  # type: ignore[operator]
        stale_ids: list[str] = []
        for name in ("S1", "S2"):
            account, _user, _token = create_identity(session, settings, name=name)  # type: ignore[arg-type]
            hold = reserve_budget(
                session,
                settings=settings,  # type: ignore[arg-type]
                account_id=account.id,
                logical_request_id=f"stale-{name}",
                stage="execution",
                amount_micro=100,
            )
            session.commit()
            hold.created_at = expired_at
            session.commit()
            stale_ids.append(hold.id)
        account, _user, _token = create_identity(session, settings, name="Fresh")  # type: ignore[arg-type]
        fresh = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="fresh-hold",
            stage="execution",
            amount_micro=100,
        )
        session.commit()
        fresh_id = fresh.id

    with factory() as session:  # type: ignore[operator]
        assert reclaim_stale_reservations(session) == 2
        session.commit()
        for stale_id in stale_ids:
            row = session.get(BudgetReservation, stale_id)
            assert row is not None and row.status == "unknown"
        untouched = session.get(BudgetReservation, fresh_id)
        assert untouched is not None and untouched.status == "reserved"
        assert reclaim_stale_reservations(session) == 0


def test_reclaim_sweep_respects_batch_limit(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    expired_at = datetime.now(UTC) - timedelta(seconds=RESERVATION_LEASE_SECONDS + 10)
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="Batch")  # type: ignore[arg-type]
        for i in range(3):
            hold = reserve_budget(
                session,
                settings=settings,  # type: ignore[arg-type]
                account_id=account.id,
                logical_request_id=f"batch-{i}",
                stage="execution",
                amount_micro=10,
            )
            session.commit()
            hold.created_at = expired_at
            session.commit()

    with factory() as session:  # type: ignore[operator]
        # limit is the per-batch size; one sweep drains every expired hold across batches.
        assert reclaim_stale_reservations(session, limit=2) == 3
        session.commit()
        assert reclaim_stale_reservations(session, limit=2) == 0


def _seed_search_fixture(factory, settings, count: int) -> Principal:  # type: ignore[no-untyped-def]
    with factory() as session:
        account, user, _token = create_identity(session, settings, name=f"Search{count}")  # type: ignore[arg-type]
        for i in range(count):
            conv = Conversation(account_id=account.id, user_id=user.id, title=f"untitled {i}")
            session.add(conv)
            session.flush()
            session.add(
                ChatMessage(
                    conversation_id=conv.id,
                    account_id=account.id,
                    role="user",
                    status="completed",
                    content=f"needle body {i}",
                )
            )
        session.commit()
        return Principal(user_id=user.id, account_id=account.id, role=user.role)


def _search_with_statement_count(engine, factory, principal: Principal) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        with factory() as session:
            results = search_conversations(session, principal, "needle")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return len(results), len(statements)


def test_search_query_count_does_not_grow_with_result_count(
    test_context: dict[str, object],
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    engine = test_context["engine"]
    small = _seed_search_fixture(factory, settings, 2)  # type: ignore[arg-type]
    small_results, small_queries = _search_with_statement_count(engine, factory, small)  # type: ignore[arg-type]
    large = _seed_search_fixture(factory, settings, 12)  # type: ignore[arg-type]
    large_results, large_queries = _search_with_statement_count(engine, factory, large)  # type: ignore[arg-type]

    assert small_results == 2
    assert large_results == 12
    assert large_queries == small_queries
