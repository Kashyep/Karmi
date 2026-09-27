from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.models import Account, Subscription, User
from daily_agent.security import issue_development_token
from daily_agent.telemetry.collector import TelemetryCollector
from daily_agent.wiring import build_routing_runtime


@pytest.fixture
def test_context(tmp_path: Path) -> Generator[dict[str, object], None, None]:
    db_path = tmp_path / "test.db"
    engine: Engine = create_engine(
        f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{db_path}",
        auth_secret="test-secret-with-enough-entropy",
        webhook_secret="test-webhook-secret",
        global_daily_budget_micro=10_000,
        router_policy_dir=tmp_path / "policies",
        telemetry_spool_path=tmp_path / "telemetry-spool.jsonl",
        telemetry_export_dir=tmp_path / "telemetry-exports",
        telemetry_flush_interval_seconds=0.05,
    )

    def session_override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    # Telemetry writes to the per-test database and spool, never the process default engine.
    telemetry = TelemetryCollector(
        session_factory=factory,
        queue_size=settings.telemetry_queue_size,
        batch_size=settings.telemetry_batch_size,
        flush_interval_seconds=settings.telemetry_flush_interval_seconds,
        spool_path=settings.telemetry_spool_path,
        attribution_window_seconds=settings.telemetry_attribution_window_seconds,
    )
    app.state.telemetry = telemetry
    app.state.routing = build_routing_runtime(settings)
    with TestClient(app) as client:
        yield {
            "app": app,
            "client": client,
            "engine": engine,
            "factory": factory,
            "settings": settings,
            "telemetry": telemetry,
        }
    engine.dispose()


def create_identity(
    session: Session, settings: Settings, *, name: str, role: str = "customer"
) -> tuple[Account, User, str]:
    account = Account(name=f"{name} account")
    session.add(account)
    session.flush()
    user = User(account_id=account.id, display_name=name, role=role)
    session.add_all([user, Subscription(account_id=account.id)])
    session.commit()
    token = issue_development_token(user, settings)
    return account, user, token

