from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from daily_agent.gateway.health import HealthTracker
from daily_agent.gateway.registry import ModelRegistry, RegistryModel, parse_registry
from daily_agent.gateway.service import (
    BASE_SYSTEM_PROMPT,
    SYSTEM_PROMPT_MAX_CHARS,
    Gateway,
    build_system_prompt,
)
from daily_agent.gateway.types import ChatRequest, ChatResult, TaskType
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.providers import ProviderCall
from daily_agent.schemas import (
    HistoryTurn,
    MessageCreate,
    RegenerateCreate,
)
from daily_agent.services import (
    HISTORY_REQUEST_CAP_BYTES,
    history_tokens,
    message_request_hash,
    trim_history,
)

FIXED_NOW = datetime(2026, 10, 21, 16, 23, tzinfo=UTC)


class FakeChatProvider:
    name: str = "openrouter"

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    def complete(self, request: ChatRequest, model: RegistryModel) -> ChatResult:
        self.requests.append(request)
        call = ProviderCall(
            provider="openrouter",
            model_id=model.model_id,
            operation="generate",
            input_tokens=10,
            output_tokens=5,
            cost_micro=0,
            measurement="registry-free-model",
            rate_version=f"registry-{model.snapshot_date}",
        )
        return ChatResult(text="ok", finish_reason="stop", latency_ms=1.0, call=call)


def entry(model_id: str, model_class: str = "economy", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "model_id": model_id,
        "provider": "openrouter",
        "class": model_class,
        "prompt_price_usd": "0",
        "completion_price_usd": "0",
        "context_length": 32_000,
        "private_data_allowed": False,
        "data_terms": "unknown",
        "scores": {},
    }
    row.update(overrides)
    return row


def make_registry(*rows: dict[str, Any]) -> ModelRegistry:
    return parse_registry(
        {"schema_version": "model-registry.v1", "snapshot_date": "2026-10-18", "models": list(rows)}
    )


def test_build_system_prompt_date_line() -> None:
    prompt = build_system_prompt(FIXED_NOW)
    expected_suffix = (
        "\nCurrent date and time: Wednesday, 21 October 2026, 21:53 IST (Asia/Kolkata, UTC+05:30)."
    )
    assert prompt.endswith(expected_suffix)
    assert prompt.startswith(BASE_SYSTEM_PROMPT)
    assert len(prompt) <= SYSTEM_PROMPT_MAX_CHARS

    prompt_rollover = build_system_prompt(datetime(2026, 10, 21, 18, 45, tzinfo=UTC))
    assert "Thursday, 22 October 2026, 00:15 IST" in prompt_rollover


def test_gateway_with_fake_provider_formats_messages_and_system_prompt() -> None:
    provider = FakeChatProvider()
    reg = make_registry(entry("vendor/m:free"))
    gateway = Gateway(
        registry=reg,
        providers={"openrouter": provider},
        health=HealthTracker(),
        clock=lambda: FIXED_NOW,
    )

    history = (
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "Paris."},
    )
    result = gateway.generate(
        plan=SYNTHETIC_POLICIES["ananta"],
        text="And of Germany?",
        task_type=TaskType.STUDY,
        max_output_tokens=100,
        history=history,
    )

    assert not result.failed
    assert result.text == "ok"
    assert len(provider.requests) == 1
    messages = provider.requests[0].messages
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0]["content"] == build_system_prompt(FIXED_NOW)
    assert messages[1] == {"role": "user", "content": "What is the capital of France?"}
    assert messages[2] == {"role": "assistant", "content": "Paris."}
    assert messages[3] == {"role": "user", "content": "And of Germany?"}

    provider.requests.clear()
    result_no_history = gateway.generate(
        plan=SYNTHETIC_POLICIES["ananta"],
        text="Solo question",
        task_type=TaskType.STUDY,
        max_output_tokens=100,
        history=(),
    )
    assert not result_no_history.failed
    assert len(provider.requests) == 1
    no_hist_messages = provider.requests[0].messages
    assert len(no_hist_messages) == 2
    assert [m["role"] for m in no_hist_messages] == ["system", "user"]
    assert no_hist_messages[0]["content"] == build_system_prompt(FIXED_NOW)
    assert no_hist_messages[1] == {"role": "user", "content": "Solo question"}


def test_prompt_tokens_includes_history_routes_or_fails_context_check() -> None:
    # prompt_tokens = (len(text) + len(system) + history_bytes) // 4.
    # With len(text)=10, len(system)=675, max_output_tokens=100:
    # Text alone: (10 + 675) // 4 = 171 prompt tokens -> needed = 171 + 100 = 271.
    # Text + 4000-byte history: (10 + 675 + 4000) // 4 = 1171 prompt tokens -> needed = 1271.
    # A model with context_length=500 accommodates text alone (271 <= 500) but rejects text + history (1271 > 500).
    provider = FakeChatProvider()
    reg = make_registry(entry("vendor/tiny-context:free", "economy", context_length=500))
    gateway = Gateway(
        registry=reg,
        providers={"openrouter": provider},
        health=HealthTracker(),
        clock=lambda: FIXED_NOW,
    )

    r1 = gateway.generate(
        plan=SYNTHETIC_POLICIES["ananta"],
        text="short text",
        task_type=TaskType.STUDY,
        max_output_tokens=100,
        history=(),
    )
    assert not r1.failed
    assert r1.text == "ok"

    history = [{"role": "user", "content": "h" * 4000}]
    r2 = gateway.generate(
        plan=SYNTHETIC_POLICIES["ananta"],
        text="short text",
        task_type=TaskType.STUDY,
        max_output_tokens=100,
        history=history,
    )
    assert r2.failed
    assert r2.reason == "no_eligible_model"


def test_trim_history() -> None:
    plan = SYNTHETIC_POLICIES["ananta"]  # input_tokens = 4000 -> 16000 bytes cap

    # 1. Everything kept when it fits
    t1 = HistoryTurn(role="user", content="hello")
    t2 = HistoryTurn(role="assistant", content="world")
    assert trim_history([t1, t2], text="query", plan=plan) == (t1, t2)

    # 2. Oldest dropped first with an exact expected tuple
    # Budget = 16000 - SYSTEM_PROMPT_MAX_CHARS (~675) - 10000 = ~5325 bytes
    text = "x" * 10_000
    turn_old = HistoryTurn(role="user", content="a" * 3000)
    turn_mid = HistoryTurn(role="assistant", content="b" * 3000)
    turn_new = HistoryTurn(role="user", content="c" * 2000)
    trimmed_dropped = trim_history([turn_old, turn_mid, turn_new], text=text, plan=plan)
    assert trimmed_dropped == (turn_mid, turn_new)

    # 3. Contiguous suffix: a too-big middle turn stops trimming even if an older small turn fits
    turn_small_old = HistoryTurn(role="user", content="tiny")
    turn_big_mid = HistoryTurn(role="assistant", content="m" * 5000)
    turn_small_new = HistoryTurn(role="user", content="recent" * 200)  # 1200 bytes
    trimmed_suffix = trim_history(
        [turn_small_old, turn_big_mid, turn_small_new], text=text, plan=plan
    )
    assert trimmed_suffix == (turn_small_new,)

    # 4. Returns () when text fills the budget
    text_fills_budget = "x" * 16_000
    assert trim_history([t1, t2], text=text_fills_budget, plan=plan) == ()

    # 5. Capped by HISTORY_REQUEST_CAP_BYTES for the parth plan with 20 x 8000-char turns
    parth_plan = SYNTHETIC_POLICIES["parth"]  # input_tokens = 32_000 -> total 40_000 cap bytes
    turns_20 = [
        HistoryTurn(
            role="user" if i % 2 == 0 else "assistant",
            content=f"turn_{i:02d}_" + "z" * 7992,
        )
        for i in range(20)
    ]
    parth_trimmed = trim_history(turns_20, text="short query", plan=parth_plan)
    assert len(parth_trimmed) > 0
    assert parth_trimmed == tuple(turns_20[-len(parth_trimmed) :])
    assert sum(len(t.content.encode("utf-8")) for t in parth_trimmed) <= HISTORY_REQUEST_CAP_BYTES
    assert len(parth_trimmed) == 4

    # 6. History tokens value check
    sample_turns = [
        HistoryTurn(role="user", content="a" * 200),
        HistoryTurn(role="assistant", content="b" * 203),
    ]
    # Total utf-8 bytes = 403. 403 // 4 = 100.
    assert history_tokens(sample_turns) == 100


def test_message_request_hash() -> None:
    text = "Explain photosynthesis"
    expected_no_hist = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # No or empty history matches sha256(text)
    assert message_request_hash(text) == expected_no_hist
    assert message_request_hash(text, ()) == expected_no_hist
    assert message_request_hash(text, []) == expected_no_hist

    t1 = HistoryTurn(role="user", content="What is biology?")
    t2 = HistoryTurn(role="assistant", content="The study of life.")
    t3 = HistoryTurn(role="user", content="Tell me more.")
    t4 = HistoryTurn(role="assistant", content="What is biology?")  # different role

    h_with_t1 = message_request_hash(text, [t1])
    h_with_t2 = message_request_hash(text, [t2])
    h_with_t1_t2 = message_request_hash(text, [t1, t2])
    h_with_t3 = message_request_hash(text, [t3])
    h_with_t4 = message_request_hash(text, [t4])

    # With-history != without
    assert h_with_t1 != expected_no_hist

    # Different content or role -> different hash
    assert h_with_t1 != h_with_t3
    assert h_with_t1 != h_with_t4
    assert h_with_t1 != h_with_t2
    assert h_with_t1 != h_with_t1_t2

    # Same history -> same hash
    h_identical = message_request_hash(
        text, [HistoryTurn(role="user", content="What is biology?")]
    )
    assert h_with_t1 == h_identical


def test_schema_history_validation() -> None:
    # MessageCreate without history defaults to []
    msg_default = MessageCreate(text="test query", idempotency_key="key-12345678")
    assert msg_default.history == []

    for cls in (MessageCreate, RegenerateCreate):
        # 21 turns -> ValidationError
        with pytest.raises(ValidationError):
            cls(
                text="test query",
                idempotency_key="key-12345678",
                history=[
                    HistoryTurn(role="user", content=f"msg {i}") for i in range(21)
                ],
            )

        # 8001-char turn -> ValidationError
        with pytest.raises(ValidationError):
            cls(
                text="test query",
                idempotency_key="key-12345678",
                history=[{"role": "user", "content": "x" * 8001}],
            )

        # Empty content -> ValidationError
        with pytest.raises(ValidationError):
            cls(
                text="test query",
                idempotency_key="key-12345678",
                history=[{"role": "user", "content": ""}],
            )

        # Role "system" -> ValidationError
        with pytest.raises(ValidationError):
            cls(
                text="test query",
                idempotency_key="key-12345678",
                history=[{"role": "system", "content": "not allowed"}],
            )

        # 20 turns of 8000 chars accepted
        accepted_turns = [
            HistoryTurn(
                role="user" if i % 2 == 0 else "assistant",
                content="a" * 8000,
            )
            for i in range(20)
        ]
        valid_instance = cls(
            text="test query",
            idempotency_key="key-12345678",
            history=accepted_turns,
        )
        assert len(valid_instance.history) == 20
