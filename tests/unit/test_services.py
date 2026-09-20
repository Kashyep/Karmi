
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from daily_agent.config import Settings
from daily_agent.models import (
    BudgetReservation,
    PlatformBudget,
    Subscription,
    UsagePeriod,
    UsageWindow,
)
from daily_agent.services import (
    RESERVATION_LEASE_SECONDS,
    BudgetDenied,
    ReservationInFlight,
    release_budget,
    reserve_budget,
    settle_budget,
    subscription_period,
)
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
        # A live RESERVED hold blocks the duplicate key outright.
        with pytest.raises(ReservationInFlight):
            reserve_budget(
                session,
                settings=settings,  # type: ignore[arg-type]
                account_id=account.id,
                logical_request_id="logical-0001",
                stage="execution",
                amount_micro=1_000,
            )
        settle_budget(session, first, attempt_id="attempt-1", actual_micro=None)
        # Once settled, a repeat reserve returns the same row without spending.
        second = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="logical-0001",
            stage="execution",
            amount_micro=1_000,
        )
        assert second.id == first.id
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


def test_release_refunds_reserved_spend(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        reservation = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="release-1",
            stage="execution",
            amount_micro=1_000,
        )
        session.commit()
        release_budget(session, reservation)
        session.commit()
        reservation = session.get(BudgetReservation, reservation.id)
        assert reservation is not None
        assert reservation.status == "released"
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert window is not None
        assert window.reserved_micro == 0 and window.everyday_used == 0
        period = session.scalar(select(UsagePeriod).where(UsagePeriod.account_id == account.id))
        assert period is not None and period.reserved_micro == 0
        # Releasing again is a no-op, not a double refund.
        release_budget(session, reservation)
        session.commit()
        assert window.reserved_micro == 0


def test_period_anchors_to_subscription_start(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.period_anchor = date(2020, 1, 15)
        reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="anchor-1",
            stage="execution",
            amount_micro=1_000,
        )
        session.commit()
        period = session.scalar(select(UsagePeriod).where(UsagePeriod.account_id == account.id))
        assert period is not None
        expected_key, expected_reset = subscription_period(date(2020, 1, 15))
        assert period.period_key == expected_key
        assert len(expected_key) == 10  # ISO start date, not a calendar month key
        assert period.reset_at.replace(tzinfo=UTC) == expected_reset


def test_subscription_period_clamps_to_short_months() -> None:
    # Day-31 anchor clamps to month length; the anniversary not yet reached
    # means the current period started last month.
    key, reset = subscription_period(date(2024, 1, 31), datetime(2024, 2, 20, tzinfo=UTC))
    assert key == "2024-01-31"
    assert reset == datetime(2024, 2, 29, tzinfo=UTC)
    key, reset = subscription_period(date(2024, 1, 31), datetime(2024, 3, 5, tzinfo=UTC))
    assert key == "2024-02-29"
    assert reset == datetime(2024, 3, 31, tzinfo=UTC)
    key, reset = subscription_period(date(2024, 1, 20), datetime(2024, 1, 10, tzinfo=UTC))
    assert key == "2023-12-20"
    assert reset == datetime(2024, 1, 20, tzinfo=UTC)


def test_retry_after_release_re_reserves(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        first = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="retry-1",
            stage="execution",
            amount_micro=1_000,
        )
        release_budget(session, first)
        session.commit()
        # Retrying the same key must re-reserve capacity, not bypass budgets.
        retry = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="retry-1",
            stage="execution",
            amount_micro=1_000,
        )
        session.commit()
        assert retry.id == first.id
        assert retry.status == "reserved"
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        period = session.scalar(select(UsagePeriod).where(UsagePeriod.account_id == account.id))
        assert window is not None and period is not None
        assert window.reserved_micro == 1_000 and window.everyday_used == 1
        assert period.reserved_micro == 1_000
        settle_budget(session, retry, attempt_id="a:1", actual_micro=100)
        session.commit()
        assert window.settled_micro == 100


def test_stale_reservation_is_reclaimed_and_charged(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        stale = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="dead-worker",
            stage="execution",
            amount_micro=2_000,
        )
        # Simulate the owning worker dying: age the hold past its lease.
        stale.created_at = datetime.now(UTC) - timedelta(seconds=RESERVATION_LEASE_SECONDS + 10)
        session.commit()
        # A retry of the same key reclaims it: the abandoned hold is charged
        # as unknown spend, then the row re-reserves fresh capacity.
        retry = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="dead-worker",
            stage="execution",
            amount_micro=500,
        )
        session.commit()
        assert retry.id == stale.id and retry.status == "reserved"
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert window is not None
        assert window.settled_micro == 2_000  # abandoned hold charged at estimate
        assert window.reserved_micro == 500


def test_reclaim_sweeps_other_stale_holds_in_window(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        stale = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="abandoned",
            stage="execution",
            amount_micro=1_500,
        )
        stale.created_at = datetime.now(UTC) - timedelta(seconds=RESERVATION_LEASE_SECONDS + 10)
        session.commit()
        # An unrelated reservation for the account sweeps the stale hold.
        reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="fresh-1",
            stage="execution",
            amount_micro=100,
        )
        session.commit()
        swept = session.get(BudgetReservation, stale.id)
        assert swept is not None and swept.status == "unknown"
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert window is not None
        assert window.settled_micro == 1_500
        assert window.reserved_micro == 100
