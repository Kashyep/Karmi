from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import Generator
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import get_session
from daily_agent.models import BugReport
from tests.conftest import create_identity

pytestmark = pytest.mark.integration


def integration_urls() -> tuple[str, str]:
    database_url = os.environ.get("DAILY_AGENT_INTEGRATION_DATABASE_URL", "")
    redis_url = os.environ.get("DAILY_AGENT_INTEGRATION_REDIS_URL", "")
    if not database_url:
        pytest.skip("DAILY_AGENT_INTEGRATION_DATABASE_URL not set; disposable PostgreSQL required.")
    if "127.0.0.1:55432/daily_agent_test" not in database_url:
        pytest.fail("refusing to run outside the declared disposable PostgreSQL database")
    if redis_url != "redis://127.0.0.1:56379/15":
        pytest.fail("refusing to run outside the declared disposable Redis database")
    return database_url, redis_url


def sample_diagnostics() -> dict[str, Any]:
    return {
        "app_version": "0.1.0",
        "build_number": "5",
        "git_sha": "abc1234",
        "os": "android",
        "os_version": "16",
        "device_model": "Pixel 9a",
        "locale": "en-IN",
        "text_scale": 1.0,
        "theme": "dark",
        "reduce_transparency": False,
        "plan": "ananta",
        "screen": "chat",
        "recent_request_ids": ["req-1", "req-2"],
        "recent_error_codes": ["timeout"],
        "run_id": "run-test-1",
        "error_code": "E_TIMEOUT",
    }


@pytest.fixture(scope="module")
def pg_engine() -> Generator[Engine, None, None]:
    database_url, _redis_url = integration_urls()
    os.environ["DAILY_AGENT_DATABASE_URL"] = database_url
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "head")

    engine = create_engine(
        database_url,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(pg_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest.fixture
def test_settings() -> Settings:
    database_url, _redis_url = integration_urls()
    return Settings(
        environment="test",
        database_url=database_url,
        auth_secret="integration-fixture-secret",
        webhook_secret="integration-webhook-secret",
    )


@pytest.fixture
def test_app(session_factory: sessionmaker[Session], test_settings: Settings) -> FastAPI:
    def session_override() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: test_settings
    return app


@pytest.fixture(autouse=True)
def clean_bug_reports(session_factory: sessionmaker[Session]) -> Generator[None, None, None]:
    with session_factory() as session:
        session.execute(delete(BugReport))
        session.commit()
    yield
    with session_factory() as session:
        session.execute(delete(BugReport))
        session.commit()


def test_five_concurrent_bug_reports_from_one_user_yield_three_created_and_two_limited(
    session_factory: sessionmaker[Session],
    test_settings: Settings,
    test_app: FastAPI,
) -> None:
    with session_factory() as session:
        _account, user, token = create_identity(
            session, test_settings, name="concurrent_single_user"
        )

    headers = {"Authorization": f"Bearer {token}"}
    payloads = [
        {
            "client_report_id": str(uuid.uuid4()),
            "category": "chat",
            "description": f"Concurrent test report {i}",
            "diagnostics": sample_diagnostics(),
        }
        for i in range(5)
    ]

    async def run_concurrent() -> list[httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            tasks = [
                client.post("/v1/bug-reports", headers=headers, json=payloads[i])
                for i in range(5)
            ]
            return await asyncio.gather(*tasks)

    responses = asyncio.run(run_concurrent())
    status_codes = sorted(r.status_code for r in responses)
    assert status_codes == [201, 201, 201, 429, 429]

    limited_responses = [r for r in responses if r.status_code == 429]
    assert len(limited_responses) == 2
    for resp in limited_responses:
        assert "retry-after" in resp.headers
        retry_after = int(resp.headers["retry-after"])
        assert retry_after > 0

    created_responses = [r for r in responses if r.status_code == 201]
    assert len(created_responses) == 3
    for resp in created_responses:
        data = resp.json()
        assert data["status"] == "new"
        assert re.match(r"^KARMI-\d{4}$", data["ticket"]) is not None

    with session_factory() as session:
        user_reports = session.scalars(
            select(BugReport).where(BugReport.user_id == user.id)
        ).all()
        assert len(user_reports) == 3
        count = session.scalar(
            select(func.count(BugReport.id)).where(BugReport.user_id == user.id)
        )
        assert count == 3


def test_concurrent_ticket_allocation_across_users_is_unique_and_never_500(
    session_factory: sessionmaker[Session],
    test_settings: Settings,
    test_app: FastAPI,
) -> None:
    num_users = 8
    users_data: list[tuple[Any, str]] = []
    with session_factory() as session:
        for i in range(num_users):
            _account, user, token = create_identity(
                session, test_settings, name=f"concurrent_ticket_user_{i}_{uuid.uuid4().hex[:6]}"
            )
            users_data.append((user, token))

    async def run_concurrent() -> list[httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            tasks = [
                client.post(
                    "/v1/bug-reports",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "client_report_id": str(uuid.uuid4()),
                        "category": "chat",
                        "description": f"Concurrent report from user {i}",
                        "diagnostics": sample_diagnostics(),
                    },
                )
                for i, (_user, token) in enumerate(users_data)
            ]
            return await asyncio.gather(*tasks)

    responses = asyncio.run(run_concurrent())

    for resp in responses:
        assert resp.status_code != 500, f"Got 500: {resp.text}"
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    tickets = [r.json()["ticket"] for r in responses]
    assert len(tickets) == num_users
    assert len(set(tickets)) == num_users

    ticket_pattern = re.compile(r"^KARMI-\d{4}$")
    for ticket in tickets:
        assert ticket_pattern.match(ticket) is not None, f"Ticket {ticket} did not match KARMI-\\d{{4}}"

    user_ids = [u.id for u, _ in users_data]
    with session_factory() as session:
        reports = session.scalars(
            select(BugReport).where(BugReport.user_id.in_(user_ids))
        ).all()
        assert len(reports) == num_users
        ticket_numbers = {r.ticket_number for r in reports}
        assert len(ticket_numbers) == num_users


def test_concurrent_ticket_allocation_multiple_users_under_limit(
    session_factory: sessionmaker[Session],
    test_settings: Settings,
    test_app: FastAPI,
) -> None:
    num_users = 3
    users_data: list[tuple[Any, str]] = []
    with session_factory() as session:
        for i in range(num_users):
            _account, user, token = create_identity(
                session, test_settings, name=f"multi_user_report_{i}_{uuid.uuid4().hex[:6]}"
            )
            users_data.append((user, token))

    requests_to_fire: list[tuple[str, dict[str, Any]]] = []
    for user_idx, (_user, token) in enumerate(users_data):
        for req_idx in range(2):
            requests_to_fire.append(
                (
                    token,
                    {
                        "client_report_id": str(uuid.uuid4()),
                        "category": "ui",
                        "description": f"User {user_idx} concurrent report {req_idx}",
                        "diagnostics": sample_diagnostics(),
                    },
                )
            )

    async def run_concurrent() -> list[httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            tasks = [
                client.post(
                    "/v1/bug-reports",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
                for token, payload in requests_to_fire
            ]
            return await asyncio.gather(*tasks)

    responses = asyncio.run(run_concurrent())
    assert len(responses) == 6
    for resp in responses:
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    tickets = [r.json()["ticket"] for r in responses]
    assert len(tickets) == 6
    assert len(set(tickets)) == 6

    ticket_pattern = re.compile(r"^KARMI-\d{4}$")
    for ticket in tickets:
        assert ticket_pattern.match(ticket) is not None, f"Ticket {ticket} did not match KARMI-\\d{{4}}"

    with session_factory() as session:
        for user, _token in users_data:
            user_reports = session.scalars(
                select(BugReport).where(BugReport.user_id == user.id)
            ).all()
            assert len(user_reports) == 2
