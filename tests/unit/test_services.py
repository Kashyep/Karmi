
import pytest
from sqlalchemy import select

from daily_agent.config import Settings
from daily_agent.models import (
    BudgetReservation,
    PlatformBudget,
    UsagePeriod,
    UsageWindow,
)
from daily_agent.services import BudgetDenied, reserve_budget, settle_budget
from tests.conftest import create_identity


def test_reservation_is_idempotent_and_unknown_cost_is_not_zero(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        first = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="logical-0001",
            stage="execution",
            amount_micro=1_000,
        )
        second = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="logical-0001",
            stage="execution",
            amount_micro=1_000,
        )
        assert first.id == second.id
        settle_budget(session, first, attempt_id="attempt-1", actual_micro=None)
        session.commit()
        reservation = session.get(BudgetReservation, first.id)
        assert reservation is not None
        assert reservation.actual_micro is None
        assert reservation.status == "unknown"
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert window is not None
        assert window.settled_micro == 1_000


def test_account_and_platform_caps_are_separate(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings: Settings = test_context["settings"]  # type: ignore[assignment]
    settings.global_daily_budget_micro = 1_500
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")
        reserve_budget(
            session,
            settings=settings,
            account_id=account.id,
            logical_request_id="logical-0001",
            stage="execution",
            amount_micro=1_000,
        )
        session.commit()
    with factory() as session:  # type: ignore[operator]
        with pytest.raises(BudgetDenied, match="platform"):
            reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="logical-0002",
                stage="execution",
                amount_micro=1_000,
            )
        session.rollback()
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        platform = session.scalar(select(PlatformBudget))
        assert window is not None and platform is not None
        assert window.reserved_micro == 1_000
        assert platform.reserved_micro == 1_000



def test_period_cap_is_not_regranted_by_daily_window(test_context: dict[str, object]) -> None:
    # ananta: period_cost_cap=20_000, everyday_limit=20 -> the 5th reservation
    # must be denied by the period accumulator even though the daily window
    # still has count/spend headroom.
    factory = test_context["factory"]
    settings: Settings = test_context["settings"]  # type: ignore[assignment]
    settings.global_daily_budget_micro = 1_000_000
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")
        for i in range(4):
            reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id=f"period-{i}",
                stage="execution",
                amount_micro=5_000,
            )
        session.commit()
    with factory() as session:  # type: ignore[operator]
        with pytest.raises(BudgetDenied, match="period"):
            reserve_budget(
                session,
                settings=settings,
                account_id=account.id,
                logical_request_id="period-5",
                stage="execution",
                amount_micro=5_000,
            )
        session.rollback()
        period = session.scalar(
            select(UsagePeriod).where(UsagePeriod.account_id == account.id)
        )
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert period is not None and window is not None
        assert period.reserved_micro == 20_000
        assert window.everyday_used == 4


def test_settle_updates_period_counters(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        reservation = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="settle-1",
            stage="execution",
            amount_micro=1_000,
        )
        settle_budget(session, reservation, attempt_id="attempt-1", actual_micro=100)
        session.commit()
        period = session.scalar(
            select(UsagePeriod).where(UsagePeriod.account_id == account.id)
        )
        assert period is not None
        assert period.reserved_micro == 0
        assert period.settled_micro == 100
