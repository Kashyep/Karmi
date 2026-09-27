from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from daily_agent.models import Account, Subscription, User
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.services import (
    PLAN_TO_TIER,
    TIER_TO_PLAN,
    plan_for_tier,
    sync_account_progression,
    sync_theme_progression,
    tier_for_plan,
)
from tests.conftest import create_identity


def test_plan_to_tier_mapping() -> None:
    assert tier_for_plan("ananta") == 1
    assert tier_for_plan("yanta") == 2
    assert tier_for_plan("trika") == 3
    assert tier_for_plan("parth") == 4
    assert tier_for_plan("nonexistent") == 1

    assert plan_for_tier(1) == "ananta"
    assert plan_for_tier(2) == "yanta"
    assert plan_for_tier(3) == "trika"
    assert plan_for_tier(4) == "parth"
    assert plan_for_tier(99) == "ananta"

    assert PLAN_TO_TIER["ananta"] == 1
    assert PLAN_TO_TIER["yanta"] == 2
    assert PLAN_TO_TIER["trika"] == 3
    assert PLAN_TO_TIER["parth"] == 4

    assert TIER_TO_PLAN[1] == "ananta"
    assert TIER_TO_PLAN[2] == "yanta"
    assert TIER_TO_PLAN[3] == "trika"
    assert TIER_TO_PLAN[4] == "parth"

    # Verify synthetic policy display name for part is Parth
    assert SYNTHETIC_POLICIES["parth"].display_name == "Parth"


def test_upgrade_raises_unlocked_tier_and_keeps_active_theme(
    test_context: dict[str, object]
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _token = create_identity(session, settings, name="Upgrader")  # type: ignore[arg-type]
        assert user.unlocked_tier == 1
        assert user.active_theme == 1

        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.plan_id = "parth"
        subscription.status = "active"
        session.commit()

        sync_theme_progression(session, user)
        session.commit()

        assert user.unlocked_tier == 4
        assert user.active_theme == 1


def test_downgrade_clamps_active_theme(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _token = create_identity(session, settings, name="Downgrader")  # type: ignore[arg-type]
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.plan_id = "parth"
        subscription.status = "active"
        user.unlocked_tier = 4
        user.active_theme = 4
        session.commit()

        # Downgrade to yanta (tier 2)
        subscription.plan_id = "yanta"
        session.commit()

        sync_theme_progression(session, user)
        session.commit()

        assert user.unlocked_tier == 2
        assert user.active_theme == 2


def test_cancelled_subscription_reverts_to_tier_1(
    test_context: dict[str, object]
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _token = create_identity(session, settings, name="Canceller")  # type: ignore[arg-type]
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.plan_id = "trika"
        subscription.status = "active"
        user.unlocked_tier = 3
        user.active_theme = 3
        session.commit()

        # Cancel subscription
        subscription.status = "cancelled"
        session.commit()

        sync_theme_progression(session, user)
        session.commit()

        assert user.unlocked_tier == 1
        assert user.active_theme == 1


def test_sync_account_progression_updates_all_users_in_account(
    test_context: dict[str, object]
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user1, _token1 = create_identity(session, settings, name="User1")  # type: ignore[arg-type]
        user2 = User(
            account_id=account.id,
            display_name="User2",
            role="customer",
            unlocked_tier=1,
            active_theme=1,
        )
        session.add(user2)
        session.commit()

        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.plan_id = "parth"
        subscription.status = "active"
        user1.unlocked_tier = 4
        user1.active_theme = 4
        user2.unlocked_tier = 4
        user2.active_theme = 2
        session.commit()

        # Downgrade account to yanta (tier 2)
        subscription.plan_id = "yanta"
        sync_account_progression(session, account.id)
        session.commit()

        assert user1.unlocked_tier == 2
        assert user1.active_theme == 2  # Clamped from 4 to 2
        assert user2.unlocked_tier == 2
        assert user2.active_theme == 2  # Kept at 2 since 2 <= 2


def test_check_constraints_reject_invalid_tiers_at_db_level(
    test_context: dict[str, object]
) -> None:
    factory = test_context["factory"]
    with factory() as session:  # type: ignore[operator]
        account = Account(name="Constraint account")
        session.add(account)
        session.flush()

        # active_theme > unlocked_tier must raise IntegrityError
        invalid_user = User(
            account_id=account.id,
            display_name="Bad Theme",
            role="customer",
            unlocked_tier=1,
            active_theme=2,
        )
        session.add(invalid_user)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # unlocked_tier < 1 must raise IntegrityError
        invalid_tier_low = User(
            account_id=account.id,
            display_name="Low Tier",
            role="customer",
            unlocked_tier=0,
            active_theme=0,
        )
        session.add(invalid_tier_low)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # unlocked_tier > 4 must raise IntegrityError
        invalid_tier_high = User(
            account_id=account.id,
            display_name="High Tier",
            role="customer",
            unlocked_tier=5,
            active_theme=1,
        )
        session.add(invalid_tier_high)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # active_theme < 1 must raise IntegrityError
        invalid_theme_low = User(
            account_id=account.id,
            display_name="Low Theme",
            role="customer",
            unlocked_tier=2,
            active_theme=0,
        )
        session.add(invalid_theme_low)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # active_theme > 4 must raise IntegrityError
        invalid_theme_high = User(
            account_id=account.id,
            display_name="High Theme",
            role="customer",
            unlocked_tier=4,
            active_theme=5,
        )
        session.add(invalid_theme_high)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
