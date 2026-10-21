from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
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
    Run,
    Subscription,
    UsageWindow,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from tests.conftest import create_identity

pytestmark = pytest.mark.e2e

KEY = "test-key-synthetic"
FIXED_NOW = datetime(2026, 10, 21, 16, 23, tzinfo=UTC)


def _entry(
    model_id: str, model_class: str = "economy", *, private: bool = False, provider: str = "openrouter"
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
            *,
            clock: Callable[[], datetime] | None = None,
            **overrides: Any,
        ) -> Harness:
            db_path = tmp_path / f"chat_history_{len(engines)}.db"
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
                clock=clock or (lambda: FIXED_NOW),
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


def send(
    harness: Harness,
    token: str,
    key: str,
    text: str = "Explain photosynthesis simply",
    *,
    history: list[dict[str, str]] | None = None,
) -> httpx.Response:
    payload: dict[str, Any] = {"text": text, "idempotency_key": key}
    if history is not None:
        payload["history"] = history
    return harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )


def regenerate(
    harness: Harness,
    token: str,
    run_id: str,
    key: str,
    text: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> httpx.Response:
    payload: dict[str, Any] = {"text": text, "idempotency_key": key}
    if history is not None:
        payload["history"] = history
    return harness.client.post(
        f"/v1/runs/{run_id}/regenerate",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )


def test_kolkata_conversation(make_harness: Callable[..., Harness]) -> None:
    replies = [
        "Kolkata is in IST (UTC+05:30).",
        "Today is Wednesday.",
        "Russia spans 11 time zones.",
    ]
    seen_calls = 0

    def handler(_r: httpx.Request) -> httpx.Response:
        nonlocal seen_calls
        res = reply(replies[seen_calls])
        seen_calls += 1
        return res

    harness = make_harness([ECO_A], handler)
    _account, token = identity(harness)

    q1 = "what is the timezone of Kolkata?"
    r1 = replies[0]
    res1 = send(harness, token, "kolkata-1", q1)
    assert res1.status_code == 200
    assert res1.json()["response"] == r1

    q2 = "what's the day today?"
    r2 = replies[1]
    res2 = send(
        harness,
        token,
        "kolkata-2",
        q2,
        history=[{"role": "user", "content": q1}, {"role": "assistant", "content": r1}],
    )
    assert res2.status_code == 200
    assert res2.json()["response"] == r2

    q3 = "russia"
    res3 = send(
        harness,
        token,
        "kolkata-3",
        q3,
        history=[
            {"role": "user", "content": q1},
            {"role": "assistant", "content": r1},
            {"role": "user", "content": q2},
            {"role": "assistant", "content": r2},
        ],
    )
    assert res3.status_code == 200

    assert len(harness.seen) == 3
    third_messages = json.loads(harness.seen[2].content)["messages"]
    assert len(third_messages) == 6
    assert third_messages[0]["role"] == "system"
    assert (
        "Current date and time: Wednesday, 21 October 2026, 21:53 IST"
        in third_messages[0]["content"]
    )
    assert third_messages[1] == {"role": "user", "content": q1}
    assert third_messages[2] == {"role": "assistant", "content": r1}
    assert third_messages[3] == {"role": "user", "content": q2}
    assert third_messages[4] == {"role": "assistant", "content": r2}
    assert third_messages[5] == {"role": "user", "content": q3}


def test_no_history_field_backward_compatible(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("Light speed is c."))
    _account, token = identity(harness)

    text = "what is the speed of light?"
    res = send(harness, token, "no-hist-1", text)
    assert res.status_code == 200

    assert len(harness.seen) == 1
    messages = json.loads(harness.seen[0].content)["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": text}

    with harness.factory() as session:
        run = session.scalar(select(Run).where(Run.logical_request_id == "no-hist-1"))
        assert run is not None
        assert run.request_hash == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_idempotent_replay_and_history_conflict(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("Replay test answer."))
    _account, token = identity(harness)

    history = [{"role": "user", "content": "prev query"}, {"role": "assistant", "content": "prev ans"}]
    first = send(harness, token, "replay-key-1", "current prompt", history=history)
    assert first.status_code == 200
    first_run_id = first.json()["run_id"]
    assert len(harness.seen) == 1

    # Same key + same text + same history -> replay
    second = send(harness, token, "replay-key-1", "current prompt", history=history)
    assert second.status_code == 200
    assert second.json()["run_id"] == first_run_id
    assert len(harness.seen) == 1

    # Same key + same text + different history -> 409
    diff_history = [{"role": "user", "content": "different query"}]
    third = send(harness, token, "replay-key-1", "current prompt", history=diff_history)
    assert third.status_code == 409

    # Same key + text, with history added where the first had none -> 409
    first_no_hist = send(harness, token, "replay-key-2", "first prompt")
    assert first_no_hist.status_code == 200
    second_with_hist = send(harness, token, "replay-key-2", "first prompt", history=history)
    assert second_with_hist.status_code == 409


def test_regenerate_with_history(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("Regenerated reply."))
    _account, token = identity(harness)

    history = [{"role": "user", "content": "turn 1"}, {"role": "assistant", "content": "turn 2"}]
    init_res = send(harness, token, "regen-init-1", "main question", history=history)
    assert init_res.status_code == 200
    run_id = init_res.json()["run_id"]
    assert len(harness.seen) == 1

    # Matching text + history -> 200 and provider request contains history
    regen_ok = regenerate(
        harness, token, run_id, "regen-new-key-1", "main question", history=history
    )
    assert regen_ok.status_code == 200
    assert len(harness.seen) == 2
    regen_messages = json.loads(harness.seen[1].content)["messages"]
    assert len(regen_messages) == 4
    assert regen_messages[1] == {"role": "user", "content": "turn 1"}
    assert regen_messages[2] == {"role": "assistant", "content": "turn 2"}
    assert regen_messages[3] == {"role": "user", "content": "main question"}

    # Mismatching history -> 409
    mismatch_history = [{"role": "user", "content": "mismatched turn"}]
    regen_mismatch = regenerate(
        harness, token, run_id, "regen-new-key-2", "main question", history=mismatch_history
    )
    assert regen_mismatch.status_code == 409

    # Regenerate of a run created without history, sent without history -> 200
    no_hist_init = send(harness, token, "regen-nohist-init", "solo text")
    assert no_hist_init.status_code == 200
    no_hist_run_id = no_hist_init.json()["run_id"]

    regen_nohist = regenerate(
        harness, token, no_hist_run_id, "regen-nohist-key-1", "solo text"
    )
    assert regen_nohist.status_code == 200


def test_over_budget_history_on_ananta(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("Summarised answer."))
    account_id, token = identity(harness)

    turns = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn_{i:02d}_" + "z" * 7990}
        for i in range(20)
    ]
    prompt_text = "Summarise our conversation"
    res = send(harness, token, "over-budget-1", prompt_text, history=turns)
    assert res.status_code == 200

    assert len(harness.seen) == 1
    messages = json.loads(harness.seen[0].content)["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": prompt_text}

    # Provider receives only a contiguous newest suffix of turns that fits
    kept_turns = messages[1:-1]
    assert 0 < len(kept_turns) < 20
    assert kept_turns == turns[-len(kept_turns) :]

    # Estimated tokens of everything sent <= plan.input_tokens
    total_bytes_sent = sum(len(m["content"].encode("utf-8")) for m in messages)
    estimated_tokens = total_bytes_sent // 4
    assert estimated_tokens <= SYNTHETIC_POLICIES["ananta"].input_tokens

    # UsageWindow token accounting: settled tokens come from provider usage (12 + 4 = 16)
    window = window_of(harness, account_id)
    assert (window.tokens_settled, window.tokens_reserved, window.reserved_micro) == (16, 0, 0)


def test_chat_history_validation_422(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("ok"))
    _account, token = identity(harness)

    # 21 turns -> 422
    turns_21 = [{"role": "user", "content": f"msg {i}"} for i in range(21)]
    res_21 = send(harness, token, "val-21-key", "query", history=turns_21)
    assert res_21.status_code == 422

    # 8001-char turn -> 422
    turns_8001 = [{"role": "user", "content": "x" * 8001}]
    res_8001 = send(harness, token, "val-8001-key", "query", history=turns_8001)
    assert res_8001.status_code == 422


def test_history_is_never_logged(
    make_harness: Callable[..., Harness], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = make_harness([ECO_A], lambda _r: reply("Logged test reply."))
    _account, token = identity(harness)

    canary_string = "SUPER_DISTINCTIVE_CANARY_CHAT_HISTORY_PAYLOAD_9876543210"
    history = [
        {"role": "user", "content": canary_string},
        {"role": "assistant", "content": "Canary acknowledged."},
    ]
    res = send(harness, token, "canary-log-1", "normal user prompt", history=history)
    assert res.status_code == 200

    for record in caplog.records:
        assert canary_string not in record.getMessage()


def test_token_hold_counts_kept_history(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], lambda _r: reply("ok"))
    account_id, token = identity(harness)
    history = [{"role": "user", "content": "u" * 400}, {"role": "assistant", "content": "a" * 400}]
    assert send(harness, token, "hold-key-1", "hold check", history=history).status_code == 200
    with harness.factory() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(BudgetReservation.account_id == account_id)
        )
        assert reservation is not None
        # 10-byte text // 4 + 800 history bytes // 4, plus the plan's output allowance.
        assert reservation.reserved_tokens == 2 + 200 + SYNTHETIC_POLICIES["ananta"].output_tokens
