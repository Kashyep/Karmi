"""End-to-end tests for the disabled-by-default OpenCode generation route.

Every provider call goes through an httpx.MockTransport injected at the
``daily_agent.opencode.chat_completion`` seam, so no test can reach the network.
The API key and model are obviously synthetic.
"""

import contextlib
import json
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent import opencode
from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.models import (
    BudgetReservation,
    CostLedger,
    ReservationStatus,
    Run,
    RunStatus,
    UsageWindow,
)
from daily_agent.opencode import FREE_RATE_VERSION
from tests.conftest import create_identity

pytestmark = pytest.mark.e2e

SYNTHETIC_KEY = "test-key-synthetic"
SYNTHETIC_MODEL = "space-bunny-free"
OPENCODE_ON: dict[str, Any] = {
    "opencode_enabled": True,
    "opencode_api_key": SYNTHETIC_KEY,
    "opencode_model_id": SYNTHETIC_MODEL,
}
MESSAGE = "Write a concise hello"
DEFERRED_TEXT = "couldn't reach the AI service"


@dataclass(frozen=True)
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    settings: Settings


@pytest.fixture
def make_harness(tmp_path: Path) -> Iterator[Callable[..., Harness]]:
    with contextlib.ExitStack() as stack:
        engines: list[Engine] = []

        def build(**overrides: Any) -> Harness:
            db_path = tmp_path / "opencode.db"
            engine = create_engine(
                f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False}
            )
            engines.append(engine)
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            values: dict[str, Any] = {
                "environment": "test",
                "database_url": f"sqlite+pysqlite:///{db_path}",
                "auth_secret": "test-secret-with-enough-entropy",
                "webhook_secret": "test-webhook-secret",
                "global_daily_budget_micro": 10_000,
            }
            values.update(overrides)
            settings = Settings(**values)

            def session_override() -> Generator[Session, None, None]:
                with factory() as session:
                    yield session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[get_settings] = lambda: settings
            client = stack.enter_context(TestClient(app))
            return Harness(client=client, factory=factory, settings=settings)

        try:
            yield build
        finally:
            for engine in engines:
                engine.dispose()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def completion_payload(text: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }


def install_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Route every chat_completion call through a recording MockTransport."""
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(recording)
    original = opencode.chat_completion

    def with_transport(**kwargs: Any) -> opencode.Completion:
        return original(**kwargs, transport=transport)

    monkeypatch.setattr(opencode, "chat_completion", with_transport)
    return seen


def send(harness: Harness, token: str, key: str) -> Any:
    return harness.client.post(
        "/v1/messages", headers=auth(token), json={"text": MESSAGE, "idempotency_key": key}
    )


def assert_settled_as_unknown(harness: Harness, account_id: str, key: str) -> None:
    """A failed provider call charges the full hold as unknown cost and leaves nothing reserved."""
    with harness.factory() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.account_id == account_id,
                BudgetReservation.logical_request_id == key,
                BudgetReservation.stage == "execution",
            )
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.UNKNOWN
        assert reservation.actual_micro is None
        assert reservation.reserved_micro > 0
        ledger = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
        assert len(ledger) == 1
        assert ledger[0].provider == "opencode"
        assert ledger[0].measurement == "unknown"
        assert ledger[0].cost_micro is None
        assert ledger[0].attempt_id.endswith(":generate_failed")
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account_id))
        assert window is not None
        assert window.reserved_micro == 0
        assert window.settled_micro == reservation.reserved_micro


def test_successful_opencode_reply_is_returned_persisted_and_settled(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(**OPENCODE_ON)
    key = "request-opencode-ok-0001"
    with harness.factory() as session:
        account, _user, token = create_identity(session, harness.settings, name="A")
        account_id = account.id
    seen = install_transport(
        monkeypatch, lambda _request: httpx.Response(200, json=completion_payload("Synthetic reply."))
    )

    response = send(harness, token, key)

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Synthetic reply."
    assert body["outcome"] == "ACCEPT"
    assert body["route"] == "opencode-free"
    assert len(seen) == 1
    with harness.factory() as session:
        run = session.scalar(select(Run).where(Run.id == body["run_id"]))
        assert run is not None
        assert run.status == RunStatus.COMPLETED
        assert run.response_text == "Synthetic reply."
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.account_id == account_id,
                BudgetReservation.logical_request_id == key,
            )
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.SETTLED
        assert reservation.status != ReservationStatus.RESERVED
        assert reservation.actual_micro == 0
        ledger = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
        assert len(ledger) == 1
        assert ledger[0].provider == "opencode"
        assert ledger[0].model_id == SYNTHETIC_MODEL
        assert ledger[0].attempt_id.endswith(":generate")
        assert ledger[0].measurement == "dated-free-catalog"
        assert ledger[0].rate_version == FREE_RATE_VERSION
        assert ledger[0].cost_micro == 0
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account_id))
        assert window is not None
        assert window.reserved_micro == 0
        assert window.settled_micro == 0
        assert window.everyday_used == 1


def test_provider_http_500_returns_deferred_once_and_settles_unknown(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(**OPENCODE_ON)
    key = "request-opencode-500-0001"
    with harness.factory() as session:
        account, _user, token = create_identity(session, harness.settings, name="A")
        account_id = account.id
    seen = install_transport(
        monkeypatch, lambda _request: httpx.Response(500, json={"error": "synthetic outage"})
    )

    response = send(harness, token, key)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "DEFERRED"
    assert DEFERRED_TEXT in body["response"]
    assert body["route"] == "opencode-free"
    assert len(seen) == 1, "provider must be called exactly once with no retries"
    with harness.factory() as session:
        run = session.scalar(select(Run).where(Run.id == body["run_id"]))
        assert run is not None
        assert run.status == RunStatus.DEFERRED
    assert_settled_as_unknown(harness, account_id, key)


@pytest.mark.parametrize(
    "raw_body",
    [
        b"{}",
        b'{"choices": []}',
        b'{"choices": [{"message": {"role": "assistant"}}]}',
        b'{"choices": [{"message": {"role": "assistant", "content": "   "}}]}',
        b'{"choices": [{"message": {"role": "assistant", "content": null}}]}',
        b"<html>not json</html>",
    ],
    ids=["no-choices-key", "empty-choices", "no-content", "blank-text", "null-text", "not-json"],
)
def test_malformed_provider_output_returns_deferred_and_settles_unknown(
    make_harness: Callable[..., Harness],
    monkeypatch: pytest.MonkeyPatch,
    raw_body: bytes,
) -> None:
    harness = make_harness(**OPENCODE_ON)
    key = "request-opencode-malformed-0001"
    with harness.factory() as session:
        account, _user, token = create_identity(session, harness.settings, name="A")
        account_id = account.id
    seen = install_transport(monkeypatch, lambda _request: httpx.Response(200, content=raw_body))

    response = send(harness, token, key)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "DEFERRED"
    assert DEFERRED_TEXT in body["response"]
    assert body["route"] == "opencode-free"
    assert len(seen) == 1
    assert_settled_as_unknown(harness, account_id, key)


def test_enabled_opencode_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key is unset"):
        Settings(
            environment="test",
            database_url="sqlite+pysqlite:///:memory:",
            opencode_enabled=True,
            opencode_api_key=None,
            opencode_model_id=SYNTHETIC_MODEL,
        )


@pytest.mark.parametrize("model_id", [None, "big-pickle", "gpt-6-astra"])
def test_enabled_opencode_requires_private_data_model(model_id: str | None) -> None:
    with pytest.raises(ValueError, match="private-data terms"):
        Settings(
            environment="test",
            database_url="sqlite+pysqlite:///:memory:",
            opencode_enabled=True,
            opencode_api_key=SYNTHETIC_KEY,
            opencode_model_id=model_id,
        )


def test_enabled_opencode_with_key_and_private_model_is_accepted() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        **OPENCODE_ON,
    )
    assert settings.opencode_enabled is True
    assert settings.opencode_model_id == SYNTHETIC_MODEL


def test_provider_body_contains_only_model_messages_and_limits(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(**OPENCODE_ON)
    key = "request-opencode-privacy-0001"
    with harness.factory() as session:
        account, user, token = create_identity(session, harness.settings, name="A")
        account_id = account.id
        user_id = user.id
    seen = install_transport(
        monkeypatch, lambda _request: httpx.Response(200, json=completion_payload("Hi."))
    )

    response = send(harness, token, key)

    assert response.status_code == 200
    assert len(seen) == 1
    raw = seen[0].content.decode("utf-8")
    payload = json.loads(raw)
    assert set(payload) == {"model", "messages", "max_tokens", "temperature", "stream"}
    assert payload["model"] == SYNTHETIC_MODEL
    assert payload["stream"] is False
    assert 1 <= payload["max_tokens"] <= opencode.MAX_OUTPUT_TOKENS
    assert {message["role"] for message in payload["messages"]} <= {"system", "user", "assistant"}
    assert account_id not in raw
    assert user_id not in raw
    assert key not in raw
    assert SYNTHETIC_KEY not in raw


def test_disabled_by_default_makes_no_provider_call(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness()
    assert harness.settings.opencode_enabled is False
    with harness.factory() as session:
        _account, _user, token = create_identity(session, harness.settings, name="A")
    seen = install_transport(
        monkeypatch, lambda _request: httpx.Response(500, json={"error": "must not be called"})
    )

    response = send(harness, token, "request-opencode-off-0001")

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "fake-economy"
    assert body["outcome"] == "ACCEPT"
    assert body["response"].startswith("Draft ready:")
    assert seen == []
    with harness.factory() as session:
        opencode_rows = session.scalars(
            select(CostLedger).where(CostLedger.provider == "opencode")
        ).all()
        assert opencode_rows == []


def test_idempotent_replay_of_opencode_reply_keeps_route_and_makes_no_second_request(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(**OPENCODE_ON)
    key = "request-opencode-replay-0001"
    with harness.factory() as session:
        _account, _user, token = create_identity(session, harness.settings, name="A")
    seen = install_transport(
        monkeypatch,
        lambda _request: httpx.Response(200, json=completion_payload("Synthetic reply.")),
    )

    first = send(harness, token, key)
    replay = send(harness, token, key)

    assert first.status_code == replay.status_code == 200
    assert first.json()["route"] == "opencode-free"
    assert replay.json()["route"] == first.json()["route"]
    assert len(seen) == 1
