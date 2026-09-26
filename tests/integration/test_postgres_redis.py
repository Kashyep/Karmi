from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from daily_agent.config import Settings
from daily_agent.models import PlatformBudget, UsageWindow
from daily_agent.schemas import Outcome
from daily_agent.services import (
    BudgetDenied,
    ensure_usage_window,
    persist_completed_run,
    reserve_budget,
)
from daily_agent.worker import run_once
from tests.conftest import create_identity

pytestmark = pytest.mark.integration


def integration_urls() -> tuple[str, str]:
    database_url = os.environ.get("DAILY_AGENT_INTEGRATION_DATABASE_URL", "")
    redis_url = os.environ.get("DAILY_AGENT_INTEGRATION_REDIS_URL", "")
    if "127.0.0.1:55432/daily_agent_test" not in database_url:
        pytest.fail("refusing to run outside the declared disposable PostgreSQL database")
    if redis_url != "redis://127.0.0.1:56379/15":
        pytest.fail("refusing to run outside the declared disposable Redis database")
    return database_url, redis_url


def test_migration_redis_and_atomic_platform_budget() -> None:
    database_url, redis_url = integration_urls()
    os.environ["DAILY_AGENT_DATABASE_URL"] = database_url
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "head")
    command.check(alembic)
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        auth_secret="integration-fixture-secret",  # noqa: S106
        webhook_secret="integration-webhook-secret",  # noqa: S106
        global_daily_budget_micro=5_000,
    )
    with factory() as session:
        account, _user, _token = create_identity(session, settings, name="Concurrent")
        ensure_usage_window(session, account.id, settings)
        session.commit()

    def attempt(index: int) -> bool:
        with factory() as session:
            try:
                reserve_budget(
                    session,
                    settings=settings,
                    account_id=account.id,
                    logical_request_id=f"parallel-{index:02d}",
                    stage="execution",
                    amount_micro=1_000,
                )
                session.commit()
                return True
            except BudgetDenied:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        accepted = list(pool.map(attempt, range(10)))
    assert sum(accepted) == 5
    with factory() as session:
        platform = session.scalar(select(PlatformBudget))
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        assert platform is not None and window is not None
        assert platform.reserved_micro == 5_000
        assert window.reserved_micro == 5_000
        assert window.everyday_used == 5

    redis = Redis.from_url(redis_url, decode_responses=True)
    redis.set("daily-agent:integration:health", "ok", ex=30)
    assert redis.get("daily-agent:integration:health") == "ok"
    redis.delete("daily-agent:integration:health")
    engine.dispose()



def test_concurrent_workers_deliver_each_row_exactly_once() -> None:
    database_url, _redis_url = integration_urls()
    os.environ["DAILY_AGENT_DATABASE_URL"] = database_url
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(database_url, pool_pre_ping=True, pool_size=10)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        auth_secret="integration-fixture-secret",  # noqa: S106
        webhook_secret="integration-webhook-secret",  # noqa: S106
    )
    with factory() as session:
        account, user, _token = create_identity(session, settings, name="Workers")
        for index in range(20):
            persist_completed_run(
                session,
                account_id=account.id,
                user_id=user.id,
                logical_request_id=f"worker-race-{index:02d}",
                response="synthetic",
                outcome=Outcome.ACCEPT,
            )
        session.commit()

    delivered: list[str] = []
    now = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=5) as pool:
        counts = list(
            pool.map(lambda _i: run_once(factory, now=now, deliver=lambda k, _p: delivered.append(k)), range(5))
        )
    ours = [key for key in delivered if key.startswith(f"response:{account.id}:")]
    assert len(ours) == 20 and len(set(ours)) == 20
    assert sum(counts) >= 20
    engine.dispose()
