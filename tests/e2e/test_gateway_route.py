"""End-to-end tests for the model gateway behind ``POST /v1/messages``.

Every provider call goes through an ``httpx.MockTransport`` injected into the gateway, so no test
can reach the network. Keys, models and notes are obviously synthetic.
"""

import contextlib
import json
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.gateway import build_gateway
from daily_agent.gateway.registry import parse_registry
from daily_agent.models import (
    BudgetReservation,
    CostLedger,
    ReservationStatus,
    Run,
    RunStatus,
    Subscription,
    UsageWindow,
)
from daily_agent.parakh.telemetry import build_telemetry_batch
from tests.conftest import create_identity

pytestmark = pytest.mark.e2e

KEY = "test-key-synthetic"


def _entry(
    model_id: str, model_class: str, *, private: bool = False, provider: str = "openrouter"
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "provider": provider,
        "class": model_class,
        "prompt_price_usd": "0",
        "completion_price_usd": "0",
        "context_length": 32_000,
        "private_data_allowed": private,
        "data_terms": "no_training" if private else "unknown",
        "supports_structured_output": False,
        "scores": {},
    }


def registry(*entries: dict[str, Any]) -> Any:
    return parse_registry(
        {
            "schema_version": "model-registry.v1",
            "snapshot_date": "2026-10-18",
            "provisional": True,
            "models": list(entries),
        }
    )


ECO_A = _entry("vendor/eco-a:free", "economy")
ECO_B = _entry("vendor/eco-b:free", "economy")
BAL_PRIVATE = _entry("vendor/bal-private:free", "balanced", private=True)
ADV = _entry("vendor/adv:free", "advanced")


@dataclass(frozen=True)
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    settings: Settings
    seen: list[httpx.Request]


@pytest.fixture
def make_harness(tmp_path: Path) -> Iterator[Callable[..., Harness]]:
    with contextlib.ExitStack() as stack:
        engines: list[Engine] = []

        def build(
            entries: list[dict[str, Any]],
            handler: Callable[[httpx.Request], httpx.Response],
            **overrides: Any,
        ) -> Harness:
            db_path = tmp_path / "gateway.db"
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
                "openrouter_enabled": True,
                "openrouter_api_key": KEY,
            }
            values.update(overrides)
            settings = Settings(**values)
            seen: list[httpx.Request] = []

            def recording(request: httpx.Request) -> httpx.Response:
                seen.append(request)
                return handler(request)

            def session_override() -> Generator[Session, None, None]:
                with factory() as session:
                    yield session

            app = create_app()
            app.state.gateway = build_gateway(
                settings,
                registry=registry(*entries),
                transport=httpx.MockTransport(recording),
            )
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[get_settings] = lambda: settings
            client = stack.enter_context(TestClient(app))
            return Harness(client=client, factory=factory, settings=settings, seen=seen)

        try:
            yield build
        finally:
            for engine in engines:
                engine.dispose()


def reply(text: str, *, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": finish}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )


def send(
    harness: Harness, token: str, key: str, text: str = "Explain photosynthesis simply"
) -> Any:
    return harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": text, "idempotency_key": key},
    )


def model_of(request: httpx.Request) -> str:
    return str(json.loads(request.content)["model"])


def identity(harness: Harness, plan_id: str = "ananta") -> tuple[str, str]:
    with harness.factory() as session:
        account, _user, token = create_identity(session, harness.settings, name="A")
        if plan_id != "ananta":
            subscription = session.scalar(
                select(Subscription).where(Subscription.account_id == account.id)
            )
            assert subscription is not None
            subscription.plan_id = plan_id
            session.commit()
        return account.id, token


def window_of(harness: Harness, account_id: str) -> UsageWindow:
    with harness.factory() as session:
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account_id))
        assert window is not None
        return window


def test_success_routes_to_cheapest_class_and_settles_free(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(
        [ECO_A, BAL_PRIVATE, ADV], lambda _r: reply("Plants make sugar from light.")
    )
    account_id, token = identity(harness)

    response = send(harness, token, "gw-ok-0001")

    body = response.json()
    assert response.status_code == 200
    assert body["outcome"] == "ACCEPT"
    assert body["response"] == "Plants make sugar from light."
    assert body["route"] == "openrouter/vendor/eco-a:free"
    assert [model_of(r) for r in harness.seen] == ["vendor/eco-a:free"]
    with harness.factory() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(BudgetReservation.account_id == account_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.SETTLED
        assert reservation.actual_micro == 0
        ledger = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
        assert [(row.provider, row.model_id, row.cost_micro) for row in ledger] == [
            ("openrouter", "vendor/eco-a:free", 0)
        ]
    window = window_of(harness, account_id)
    assert (window.tokens_settled, window.tokens_reserved, window.reserved_micro) == (16, 0, 0)


def test_first_model_failure_retries_once_on_a_different_model(
    make_harness: Callable[..., Harness],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if model_of(request) == "vendor/eco-a:free":
            return httpx.Response(500, json={"error": "synthetic outage"})
        return reply("Recovered answer.")

    harness = make_harness([ECO_A, ECO_B], handler)
    _account, token = identity(harness)

    body = send(harness, token, "gw-retry-0001").json()

    assert body["outcome"] == "ACCEPT"
    assert body["route"] == "openrouter/vendor/eco-b:free"
    assert [model_of(r) for r in harness.seen] == ["vendor/eco-a:free", "vendor/eco-b:free"]


def test_final_failure_defers_after_two_attempts_and_releases_the_reservation(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness([ECO_A, ECO_B, ADV], lambda _r: httpx.Response(503, json={}))
    account_id, token = identity(harness)

    response = send(harness, token, "gw-fail-0001")

    body = response.json()
    assert response.status_code == 200
    assert body["outcome"] == "DEFERRED"
    assert "couldn't reach the AI service" in body["response"]
    assert len(harness.seen) == 2, "at most one retry, never more"
    with harness.factory() as session:
        run = session.scalar(select(Run).where(Run.id == body["run_id"]))
        assert run is not None and run.status == RunStatus.DEFERRED
        reservation = session.scalar(
            select(BudgetReservation).where(BudgetReservation.account_id == account_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.RELEASED
    window = window_of(harness, account_id)
    assert (window.reserved_micro, window.settled_micro, window.everyday_used) == (0, 0, 0)
    assert (window.tokens_reserved, window.tokens_settled) == (0, 0)


def test_rejected_reply_escalates_one_class_on_the_retry(
    make_harness: Callable[..., Harness],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return reply("   ") if model_of(request) == "vendor/eco-a:free" else reply("Good answer.")

    harness = make_harness([ECO_A, ECO_B, BAL_PRIVATE], handler)
    _account, token = identity(harness, "yanta")

    body = send(harness, token, "gw-escalate-0001").json()

    assert body["outcome"] == "ACCEPT"
    assert body["route"] == "openrouter/vendor/bal-private:free"
    assert [model_of(r) for r in harness.seen] == ["vendor/eco-a:free", "vendor/bal-private:free"]


def test_rate_limited_model_is_cooled_down_for_later_requests(
    make_harness: Callable[..., Harness],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if model_of(request) == "vendor/eco-a:free":
            return httpx.Response(429, headers={"retry-after": "120"}, json={})
        return reply("Answer from B.")

    harness = make_harness([ECO_A, ECO_B], handler)
    _account, token = identity(harness)

    first = send(harness, token, "gw-429-0001").json()
    second = send(harness, token, "gw-429-0002").json()

    assert first["route"] == second["route"] == "openrouter/vendor/eco-b:free"
    assert [model_of(r) for r in harness.seen] == [
        "vendor/eco-a:free",
        "vendor/eco-b:free",
        "vendor/eco-b:free",
    ], "the cooled-down model is not called again"


def test_plan_classes_limit_which_models_are_reachable(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness([ADV, BAL_PRIVATE], lambda _r: reply("x"))
    _account, token = identity(harness)  # ananta: economy only

    body = send(harness, token, "gw-class-0001").json()

    assert body["outcome"] == "DEFERRED"
    assert harness.seen == []


def test_daily_token_quota_blocks_further_requests(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("ok"))
    account_id, token = identity(harness)
    assert send(harness, token, "gw-quota-0001").status_code == 200
    with harness.factory() as session:
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account_id))
        assert window is not None
        window.token_limit = window.tokens_settled + 10  # less than one request's hold
        session.commit()

    response = send(harness, token, "gw-quota-0002")

    assert response.status_code == 429
    assert "token quota" in json.dumps(response.json())
    assert len(harness.seen) == 1


def test_kill_switch_falls_back_to_the_demo_without_network(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("never"), gateway_kill_switch=True)
    _account, token = identity(harness)

    body = send(harness, token, "gw-kill-0001").json()

    assert body["route"] == "fake-economy"
    assert body["response"].startswith("Draft ready:")
    assert harness.seen == []


def test_idempotent_replay_keeps_route_and_makes_no_second_call(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("Stable answer."))
    _account, token = identity(harness)

    first = send(harness, token, "gw-replay-0001").json()
    second = send(harness, token, "gw-replay-0001").json()

    assert second["route"] == first["route"] == "openrouter/vendor/eco-a:free"
    assert second["run_id"] == first["run_id"]
    assert len(harness.seen) == 1


def test_export_refuses_runs_that_reference_models_missing_from_the_registry(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("Stable answer."))
    _account_id, token = identity(harness)
    send(harness, token, "gw-export-0001")
    window = (datetime.now(UTC) - timedelta(days=1), datetime.now(UTC) + timedelta(days=1))

    with harness.factory() as session:
        full = build_telemetry_batch(
            session, start=window[0], end=window[1], registry=registry(ECO_A)
        )
        assert {(m["provider"], m["model"]) for m in full["model_registry"]} >= {
            ("openrouter", "vendor/eco-a:free")
        }
        with pytest.raises(ValueError, match="absent from the registry"):
            build_telemetry_batch(session, start=window[0], end=window[1], registry=registry(ECO_B))
