from __future__ import annotations

import contextlib
import re
from typing import Any, Generator

from sqlalchemy import Engine, event

from daily_agent.models import PlatformBudget, UsagePeriod, UsageWindow
from daily_agent.services import release_budget, reserve_budget, settle_budget
from tests.conftest import create_identity

TARGET_TABLES = {
    UsageWindow.__tablename__,
    UsagePeriod.__tablename__,
    PlatformBudget.__tablename__,
}
EXPECTED_ORDER = [
    UsageWindow.__tablename__,
    UsagePeriod.__tablename__,
    PlatformBudget.__tablename__,
]


@contextlib.contextmanager
def capture_update_order(engine: Engine) -> Generator[list[str], None, None]:
    first_seen: list[str] = []

    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        match = re.search(r"\bUPDATE\s+[\"`]?([a-zA-Z0-9_]+)[\"`]?", statement, re.IGNORECASE)
        if match:
            table = match.group(1).lower()
            if table in TARGET_TABLES and table not in first_seen:
                first_seen.append(table)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield first_seen
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def test_reserve_budget_lock_order(test_context: dict[str, object]) -> None:
    engine: Engine = test_context["engine"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="ReserveLockUser")  # type: ignore[arg-type]
        with capture_update_order(engine) as update_order:
            reserve_budget(
                session,
                settings=settings,  # type: ignore[arg-type]
                account_id=account.id,
                logical_request_id="reserve-lock-1",
                stage="execution",
                amount_micro=1_000,
            )
        assert update_order == EXPECTED_ORDER


def test_settle_budget_lock_order(test_context: dict[str, object]) -> None:
    engine: Engine = test_context["engine"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="SettleLockUser")  # type: ignore[arg-type]
        reservation = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="settle-lock-1",
            stage="execution",
            amount_micro=1_000,
        )
        session.commit()
        with capture_update_order(engine) as update_order:
            settle_budget(session, reservation, attempt_id="settle-attempt-1", actual_micro=250)
            session.commit()
        assert update_order == EXPECTED_ORDER


def test_release_budget_lock_order(test_context: dict[str, object]) -> None:
    engine: Engine = test_context["engine"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="ReleaseLockUser")  # type: ignore[arg-type]
        reservation = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="release-lock-1",
            stage="execution",
            amount_micro=1_000,
        )
        session.commit()
        with capture_update_order(engine) as update_order:
            release_budget(session, reservation)
            session.commit()
        assert update_order == EXPECTED_ORDER
