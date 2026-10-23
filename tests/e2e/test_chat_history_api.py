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
    ChatMessage,
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
    model_id: str,
    model_class: str = "economy",
    *,
    private: bool = False,
    provider: str = "openrouter",
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


def sse_reply(text: str, *, finish: str = "stop") -> httpx.Response:
    payload = {
        "choices": [{"delta": {"content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }
    frames = [f"data: {json.dumps(payload)}\n\n", "data: [DONE]\n\n"]
    return httpx.Response(
        200,
        text="".join(frames),
        headers={"content-type": "text/event-stream"},
    )


def unified_handler(
    text: str, *, finish: str = "stop"
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body.get("stream"):
            return sse_reply(text, finish=finish)
        return reply(text, finish=finish)

    return handler


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

    history = [
        {"role": "user", "content": "prev query"},
        {"role": "assistant", "content": "prev ans"},
    ]
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

    regen_nohist = regenerate(harness, token, no_hist_run_id, "regen-nohist-key-1", "solo text")
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


def test_e2e_long_hindi_history_truncated_both_routes(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], unified_handler("हाँ, मैं समझ गया।"))
    _account_id, token = identity(harness)

    # Under 8000 chars (schema max) but > 4000 tokens / 16000 bytes so it exceeds the budget alone
    long_hindi_turn = "नमस्ते भारत! यह बहुत लंबा हिंदी संदेश है जो सीमा से अधिक है। " * 110
    assert len(long_hindi_turn) < 8000
    assert len(long_hindi_turn.encode("utf-8")) > 16_000
    prompt_text = "अगला सवाल"
    # 1. /v1/messages route
    res_messages = send(
        harness,
        token,
        "e2e-hindi-trunc-messages",
        prompt_text,
        history=[{"role": "assistant", "content": long_hindi_turn}],
    )
    assert res_messages.status_code == 200
    assert len(harness.seen) == 1
    sent_body_msg = json.loads(harness.seen[0].content)
    messages_1 = sent_body_msg["messages"]
    assert messages_1[0]["role"] == "system"
    assert messages_1[-1] == {"role": "user", "content": prompt_text}
    assert len(messages_1) == 3
    assert messages_1[1]["role"] == "assistant"
    assert "[…trimmed…]" in messages_1[1]["content"]

    # 2. /v1/chat/stream route
    # Create conversation with short turn 1, then a long Hindi assistant reply
    long_hindi_reply = "नमस्ते भारत! यह बहुत लंबा हिंदी संदेश है जो सीमा से अधिक है। " * 110
    harness_stream = make_harness([ECO_A], unified_handler(long_hindi_reply))
    _account_id2, token2 = identity(harness_stream)

    resp_s1 = harness_stream.client.post(
        "/v1/chat/stream",
        headers={"Authorization": f"Bearer {token2}"},
        json={"text": "पहला सवाल", "clientMessageId": "stream-hindi-01"},
    )
    assert resp_s1.status_code == 200
    conv_id = None
    for line in resp_s1.text.split("\n"):
        if line.startswith("data: ") and "conversation_id" in line:
            conv_id = json.loads(line[6:])["conversation_id"]
            break
    assert conv_id is not None

    # Now stream a follow-up in the same conversation
    resp_s2 = harness_stream.client.post(
        "/v1/chat/stream",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "text": prompt_text,
            "conversationId": conv_id,
            "clientMessageId": "stream-hindi-02",
        },
    )
    assert resp_s2.status_code == 200
    sent_body_stream = json.loads(harness_stream.seen[-1].content)
    stream_msgs = sent_body_stream["messages"]
    assert stream_msgs[0]["role"] == "system"
    assert "Asia/Kolkata" in stream_msgs[0]["content"]
    assert stream_msgs[-1] == {"role": "user", "content": prompt_text}
    assert any("[…trimmed…]" in m["content"] for m in stream_msgs[1:-1])


def scripted_handler(replies: list[tuple[str, str]]) -> Callable[[httpx.Request], httpx.Response]:
    """Answer each provider call with the next (text, finish_reason) pair, in order."""
    pending = list(replies)

    def handler(req: httpx.Request) -> httpx.Response:
        text, finish = pending.pop(0)
        if json.loads(req.content).get("stream"):
            return sse_reply(text, finish=finish)
        return reply(text, finish=finish)

    return handler


def stream_turn(
    harness: Harness,
    token: str,
    text: str,
    client_id: str,
    conversation_id: str | None = None,
) -> tuple[httpx.Response, str]:
    body: dict[str, Any] = {"text": text, "clientMessageId": client_id}
    if conversation_id is not None:
        body["conversationId"] = conversation_id
    res = harness.client.post(
        "/v1/chat/stream", headers={"Authorization": f"Bearer {token}"}, json=body
    )
    with harness.factory() as session:
        user_msg = session.scalar(
            select(ChatMessage).where(ChatMessage.client_message_id == client_id)
        )
        conv_id = user_msg.conversation_id if user_msg is not None else ""
    return res, conv_id


def sent_turns(harness: Harness, index: int) -> list[tuple[str, str]]:
    """Messages sent for request ``index`` minus the system prompt, as (role, content)."""
    messages = json.loads(harness.seen[index].content)["messages"]
    assert messages[0]["role"] == "system"
    return [(m["role"], m["content"]) for m in messages[1:]]


def reply_id(harness: Harness, user_text: str) -> str:
    """Id of the newest assistant variant answering the user message with ``user_text``."""
    with harness.factory() as session:
        user = session.scalar(
            select(ChatMessage).where(ChatMessage.role == "user", ChatMessage.content == user_text)
        )
        assert user is not None
        latest = session.scalar(
            select(ChatMessage)
            .where(ChatMessage.parent_message_id == user.id)
            .order_by(ChatMessage.variant_index.desc())
        )
        assert latest is not None
        return latest.id


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_e2e_stream_followup_includes_earlier_turn(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness([ECO_A], unified_handler("Understood."))
    _account_id, token = identity(harness)
    first_q = "My name is Rosso"
    res_1, conv_id = stream_turn(harness, token, first_q, "followup-01")
    assert res_1.status_code == 200

    second_q = "What is my name?"
    res_2, _ = stream_turn(harness, token, second_q, "followup-02", conv_id)
    assert res_2.status_code == 200
    assert len(harness.seen) == 2
    assert sent_turns(harness, 1) == [
        ("user", first_q),
        ("assistant", "Understood."),
        ("user", second_q),
    ]


def test_stream_history_excludes_other_users_and_conversations(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(
        [ECO_A],
        scripted_handler(
            [("alpha answer", "stop"), ("bravo answer", "stop"), ("gamma answer", "stop")]
        ),
    )
    _account_id, token_a = identity(harness)
    with harness.factory() as session:
        _account_b, _user_b, token_b = create_identity(session, harness.settings, name="B")

    res_a1, conv_a1 = stream_turn(harness, token_a, "alpha question", "iso-client-a1")
    assert res_a1.status_code == 200
    res_b1, _conv_b1 = stream_turn(harness, token_b, "bravo question", "iso-client-b1")
    assert res_b1.status_code == 200
    # A new conversation of user A starts with no history from conversation A1 or user B.
    res_a2, _conv_a2 = stream_turn(harness, token_a, "gamma question", "iso-client-a2")
    assert res_a2.status_code == 200
    assert sent_turns(harness, 2) == [("user", "gamma question")]

    # User B cannot reach user A's conversation at all.
    res_cross, _ = stream_turn(harness, token_b, "bravo follow-up", "iso-client-b2", conv_a1)
    assert res_cross.status_code == 404

    res_a3, _ = stream_turn(harness, token_a, "delta question", "iso-client-a3", conv_a1)
    assert res_a3.status_code == 200
    assert sent_turns(harness, 3) == [
        ("user", "alpha question"),
        ("assistant", "alpha answer"),
        ("user", "delta question"),
    ]


def test_continue_and_regenerate_send_history_without_duplicates(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(
        [ECO_A],
        scripted_handler(
            [
                ("first answer", "stop"),
                ("second answer", "length"),
                ("continued answer", "stop"),
                ("regenerated answer", "stop"),
            ]
        ),
    )
    _account_id, token = identity(harness)
    res_1, conv_id = stream_turn(harness, token, "first question", "dup-client-01")
    assert res_1.status_code == 200
    res_2, _ = stream_turn(harness, token, "second question", "dup-client-02", conv_id)
    assert res_2.status_code == 200
    prior = [("user", "first question"), ("assistant", "first answer")]
    assert sent_turns(harness, 1) == [*prior, ("user", "second question")]

    truncated_id = reply_id(harness, "second question")
    cont = harness.client.post(f"/v1/messages/{truncated_id}/continue", headers=auth(token))
    assert cont.status_code == 200
    # Continue sends the truncated reply as the assistant prefix; history stops before the turn.
    assert sent_turns(harness, 2) == [
        *prior,
        ("user", "second question"),
        ("assistant", "second answer"),
    ]

    regen = harness.client.post(f"/v1/messages/{truncated_id}/regenerate", headers=auth(token))
    assert regen.status_code == 200
    assert sent_turns(harness, 3) == [*prior, ("user", "second question")]


def test_next_turn_after_regenerate_sends_single_reply(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(
        [ECO_A],
        scripted_handler(
            [
                ("first answer", "stop"),
                ("second answer", "stop"),
                ("regenerated answer", "stop"),
                ("third answer", "stop"),
            ]
        ),
    )
    _account_id, token = identity(harness)
    res_1, conv_id = stream_turn(harness, token, "first question", "next-client-01")
    assert res_1.status_code == 200
    res_2, _ = stream_turn(harness, token, "second question", "next-client-02", conv_id)
    assert res_2.status_code == 200

    regen = harness.client.post(
        f"/v1/messages/{reply_id(harness, 'second question')}/regenerate", headers=auth(token)
    )
    assert regen.status_code == 200

    res_3, _ = stream_turn(harness, token, "third question", "next-client-03", conv_id)
    assert res_3.status_code == 200
    assert sent_turns(harness, 3) == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
        ("assistant", "regenerated answer"),
        ("user", "third question"),
    ]
