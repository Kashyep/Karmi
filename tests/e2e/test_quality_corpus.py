"""End-to-end tests for the quality corpus checking AI harness behavior over HTTP."""
from __future__ import annotations

import contextlib
import json
import os
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
from daily_agent.models import Reminder, Task
from tests.conftest import create_identity
from tests.quality_corpus import grade_response_quality, load_corpus_v1, run_corpus_live

pytestmark = pytest.mark.e2e

FIXED_NOW = datetime(2026, 10, 21, 16, 23, tzinfo=UTC)
KEY = "test-key-synthetic"


def _entry(
    model_id: str, model_class: str = "economy", *, provider: str = "openrouter"
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "provider": provider,
        "class": model_class,
        "prompt_price_usd": "0",
        "completion_price_usd": "0",
        "context_length": 32_000,
        "private_data_allowed": False,
        "data_terms": "unknown",
        "supports_structured_output": False,
        "scores": {"study": 0.9, "hindi": 0.9},
    }


def _registry(*entries: dict[str, Any]) -> Any:
    return parse_registry(
        {
            "schema_version": "model-registry.v1",
            "snapshot_date": "2026-10-18",
            "provisional": True,
            "models": list(entries),
        }
    )


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
            db_path = tmp_path / f"quality_corpus_{len(engines)}.db"
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
                registry=_registry(*entries),
                transport=httpx.MockTransport(recording),
                clock=clock or (lambda: FIXED_NOW),
            )
            app.state.settings = settings
            app.dependency_overrides[Base.metadata.create_all] = lambda: None
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[get_settings] = lambda: settings
            client = stack.enter_context(TestClient(app))
            return Harness(client=client, factory=factory, settings=settings, seen=seen)

        yield build
        for engine in engines:
            engine.dispose()


def _ok_reply(content: str = "ok") -> dict[str, Any]:
    return {
        "id": "gen-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_e2e_case_01_reference_resolution(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c1 = cases["QC-V1-01"]
    t1 = c1["turns"][0]
    t2 = c1["turns"][1]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][-1]["content"]
        if "What about the second one?" in content:
            return httpx.Response(200, json=_ok_reply(t2["mock_response"]))
        return httpx.Response(200, json=_ok_reply(t1["mock_response"]))

    harness = make_harness([_entry("vendor/eco-a:free")], handler)
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user1")

    # Turn 1
    resp1 = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": t1["user_input"], "idempotency_key": "qc-turn-1-key"},
    )
    assert resp1.status_code == 200

    # Turn 2: includes Turn 1 history
    resp2 = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": t2["user_input"],
            "idempotency_key": "qc-turn-2-key",
            "history": t2["history"],
        },
    )
    assert resp2.status_code == 200
    assert len(harness.seen) == 2

    # Check what the harness SENT over the wire for turn 2
    sent_turn_2 = json.loads(harness.seen[1].content)
    sent_messages = sent_turn_2["messages"]
    assert len(sent_messages) == 4
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == t2["history"][0]
    assert sent_messages[2] == t2["history"][1]
    assert sent_messages[3] == {"role": "user", "content": t2["user_input"]}


def test_e2e_case_02_corrections(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c2 = cases["QC-V1-02"]
    t2 = c2["turns"][1]

    harness = make_harness(
        [_entry("vendor/eco-a:free")],
        lambda _r: httpx.Response(200, json=_ok_reply(t2["mock_response"])),
    )
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user2")

    resp = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": t2["user_input"],
            "idempotency_key": "qc-c2-turn-2-key",
            "history": t2["history"],
        },
    )
    assert resp.status_code == 200
    sent = json.loads(harness.seen[0].content)
    sent_msgs = sent["messages"]
    assert len(sent_msgs) == 4
    assert sent_msgs[1]["content"] == t2["history"][0]["content"]
    assert sent_msgs[2]["content"] == t2["history"][1]["content"]
    assert sent_msgs[3]["content"] == t2["user_input"]


def test_e2e_case_03_long_hindi_followup(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c3 = cases["QC-V1-03"]
    t2 = c3["turns"][1]

    harness = make_harness(
        [_entry("vendor/eco-a:free")],
        lambda _r: httpx.Response(200, json=_ok_reply(t2["mock_response"])),
    )
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user3")

    resp = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": t2["user_input"],
            "idempotency_key": "qc-c3-key",
            "history": t2["history"],
        },
    )
    assert resp.status_code == 200
    sent = json.loads(harness.seen[0].content)
    sent_msgs = sent["messages"]
    # Verify history was kept and passed to provider
    assert len(sent_msgs) == 4
    assert sent_msgs[1]["content"] == t2["history"][0]["content"]
    assert sent_msgs[2]["content"] == t2["history"][1]["content"]


def test_e2e_case_03_long_hindi_stream_xfail(make_harness: Callable[..., Harness]) -> None:
    # Phase 1 changes streaming history. On base, stream does not send history.
    harness = make_harness(
        [_entry("vendor/eco-a:free")],
        lambda _r: httpx.Response(200, json=_ok_reply("stream reply")),
    )
    with harness.factory() as session:
        _, _, _token = create_identity(session, harness.settings, name="user3s")

    # The stream route currently sends no history on release1/chat-redesign base.
    # We mark this xfail with reason 'needs phase 1'.
    pytest.xfail("needs phase 1: stream route does not yet wire history on base")


def test_e2e_case_04_date_timezone(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c4 = cases["QC-V1-04"]

    harness = make_harness(
        [_entry("vendor/eco-a:free")],
        lambda _r: httpx.Response(200, json=_ok_reply("Today is Wednesday in IST.")),
    )
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user4")

    resp = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": c4["turns"][0]["user_input"], "idempotency_key": "qc-c4-key"},
    )
    assert resp.status_code == 200
    sent = json.loads(harness.seen[0].content)
    system_content = sent["messages"][0]["content"]
    assert "IST (Asia/Kolkata, UTC+05:30)" in system_content
    assert "Wednesday, 21 October 2026" in system_content


def test_e2e_case_05_unknown_facts(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c5 = cases["QC-V1-05"]

    harness = make_harness(
        [_entry("vendor/eco-a:free")],
        lambda _r: httpx.Response(200, json=_ok_reply(c5["turns"][0]["mock_response"])),
    )
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user5")

    resp = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": c5["turns"][0]["user_input"], "idempotency_key": "qc-c5-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "ACCEPT"
    assert "Which assignment file" in data["response"]


def test_e2e_case_06_false_action_claims(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c6 = cases["QC-V1-06"]

    harness = make_harness(
        [_entry("vendor/eco-a:free")],
        lambda _r: httpx.Response(200, json=_ok_reply(c6["turns"][0]["mock_response"])),
    )
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user6")

    resp = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": c6["turns"][0]["user_input"], "idempotency_key": "qc-c6-key"},
    )
    assert resp.status_code == 200
    sent = json.loads(harness.seen[0].content)
    sys_prompt = sent["messages"][0]["content"]
    assert "Never claim that a task, reminder or message was saved, sent or changed" in sys_prompt

    # Database verification: no tasks or reminders stored by the chat route!
    with harness.factory() as session:
        reminders = session.scalars(select(Reminder)).all()
        tasks = session.scalars(select(Task)).all()
        assert len(reminders) == 0, "Chat route must never create reminders"
        assert len(tasks) == 0, "Chat route must not create tasks"


def test_e2e_case_07_provider_fallback(make_harness: Callable[..., Harness]) -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c7 = cases["QC-V1-07"]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["model"] == "vendor/eco-a:free":
            return httpx.Response(500, json={"error": "internal upstream failure"})
        return httpx.Response(200, json=_ok_reply(c7["turns"][0]["mock_response_model_2"]))

    entries = [
        _entry("vendor/eco-a:free", "economy"),
        _entry("vendor/eco-b:free", "economy"),
    ]
    harness = make_harness(entries, handler)
    with harness.factory() as session:
        _, _, token = create_identity(session, harness.settings, name="user7")

    resp = harness.client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": c7["turns"][0]["user_input"], "idempotency_key": "qc-c7-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "ACCEPT"
    assert "x = 5" in data["response"]
    assert len(harness.seen) == 2
    assert json.loads(harness.seen[0].content)["model"] == "vendor/eco-a:free"
    assert json.loads(harness.seen[1].content)["model"] == "vendor/eco-b:free"


def test_e2e_case_08_identical_strings_recorded_bad_answer() -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c8 = cases["QC-V1-08"]
    bad = c8["recorded_bad_answer"]
    evaluation = grade_response_quality(bad["prompt"], bad["bad_response"])
    assert evaluation["status"] == "fail"
    assert evaluation["reason"] == "identical_string_echo"


def test_live_variant_gated_by_budget_cap() -> None:
    """Live model evaluation gated by KARMI_LIVE_EVAL_BUDGET.

    How to run live evaluation against OpenRouter free pool:
        KARMI_LIVE_EVAL_BUDGET=5 OPENROUTER_API_KEY=<key> \\
            .venv/bin/python -m pytest tests/e2e/test_quality_corpus.py -k test_live_variant
    """
    budget = int(os.environ.get("KARMI_LIVE_EVAL_BUDGET", "0"))
    if budget <= 0:
        pytest.skip(
            "Live evaluation skipped (KARMI_LIVE_EVAL_BUDGET=0). "
            "Set KARMI_LIVE_EVAL_BUDGET > 0 and OPENROUTER_API_KEY in settings to run live evaluation."
        )
    settings = Settings()
    if not (settings.openrouter_enabled and settings.openrouter_api_key):
        pytest.skip("OpenRouter configuration and API key are missing in settings.")

    results = run_corpus_live(budget=budget, settings=settings)
    assert len(results) <= budget
