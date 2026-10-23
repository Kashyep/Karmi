from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from daily_agent.gateway.health import HealthTracker
from daily_agent.gateway.registry import ModelRegistry, RegistryModel, parse_registry
from daily_agent.gateway.service import (
    BASE_SYSTEM_PROMPT,
    Gateway,
    build_system_prompt,
)
from daily_agent.gateway.types import ChatRequest, ChatResult, ProviderError, StreamChunk, TaskType
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.providers import ProviderCall
from daily_agent.schemas import HistoryTurn
from daily_agent.services import trim_history
from model_lab.core import candidate_record, prompt_hash, validate_cases
from tests.quality_corpus import grade_response_quality, load_corpus_v1, run_corpus_live

FIXED_NOW = datetime(2026, 10, 21, 16, 23, tzinfo=UTC)


class MockProvider:
    name: str = "openrouter"

    def __init__(self, outcomes: dict[str, Any] | None = None) -> None:
        self.requests: list[ChatRequest] = []
        self.outcomes = outcomes or {}

    def complete(self, request: ChatRequest, model: RegistryModel) -> ChatResult:
        self.requests.append(request)
        outcome = self.outcomes.get(model.model_id, "ok")
        if isinstance(outcome, Exception):
            raise outcome
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
        return ChatResult(text=str(outcome), finish_reason="stop", latency_ms=1.0, call=call)

    def stream(
        self, _request: ChatRequest, _model: RegistryModel
    ) -> Iterator[StreamChunk]:  # pragma: no cover
        yield StreamChunk(text="mock", finish_reason="stop")

def _entry(model_id: str, model_class: str = "economy", **overrides: Any) -> dict[str, Any]:
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


def _registry(*rows: dict[str, Any]) -> ModelRegistry:
    return parse_registry(
        {"schema_version": "model-registry.v1", "snapshot_date": "2026-10-18", "models": list(rows)}
    )


def test_quality_corpus_v1_validates_against_model_lab_schema() -> None:
    cases = load_corpus_v1()
    assert len(cases) == 8, f"Expected 8 corpus cases, found {len(cases)}"
    errors = validate_cases(cases)
    assert errors == [], f"Validation errors: {errors}"
    for case in cases:
        candidate = candidate_record(case)
        assert "evaluation" not in candidate
        assert "split" not in candidate
        assert candidate["prompt_hash"] == prompt_hash(case["messages"])


def test_quality_corpus_case_08_identical_strings_bad_answer_fixture() -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c8 = cases["QC-V1-08"]
    assert c8["recorded_bad_answer"]["prompt"] == "Hello, Karmi!"
    assert c8["recorded_bad_answer"]["bad_response"] == "Hello, Karmi!"
    assert c8["recorded_bad_answer"]["date"] == "2026-10-23"

    grade_bad = grade_response_quality(
        c8["recorded_bad_answer"]["prompt"],
        c8["recorded_bad_answer"]["bad_response"],
    )
    assert grade_bad["status"] == "fail"
    assert grade_bad["reason"] == "identical_string_echo"

    grade_good = grade_response_quality(
        c8["recorded_bad_answer"]["prompt"],
        "Hello! I am Karmi, your study assistant. How can I help?",
    )
    assert grade_good["status"] == "pass"


def test_harness_date_timezone_injection() -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c4 = cases["QC-V1-04"]
    prompt = build_system_prompt(FIXED_NOW)
    for expected_str in c4["harness_expectations"]["expected_system_prompt_contains"]:
        assert expected_str in prompt


def test_harness_system_prompt_forbids_action_claims() -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c6 = cases["QC-V1-06"]
    for expected_str in c6["harness_expectations"]["expected_system_prompt_contains"]:
        assert expected_str in BASE_SYSTEM_PROMPT


def test_harness_provider_fallback_unit() -> None:
    reg = _registry(
        _entry("vendor/primary:free", "economy", scores={"study": 0.9}),
        _entry("vendor/secondary:free", "economy", scores={"study": 0.8}),
    )
    provider = MockProvider(
        outcomes={"vendor/primary:free": ProviderError(ProviderError.SERVER, "service down")}
    )
    gateway = Gateway(
        registry=reg,
        providers={"openrouter": provider},
        health=HealthTracker(),
        clock=lambda: FIXED_NOW,
    )
    result = gateway.generate(
        plan=SYNTHETIC_POLICIES["ananta"],
        text="Solve for x: 3x + 12 = 27.",
        task_type=TaskType.STUDY,
        max_output_tokens=100,
        history=(),
    )
    assert not result.failed
    assert result.attempts == 2
    assert result.action == "openrouter/vendor/secondary:free"
    assert len(provider.requests) == 2


def test_harness_reference_resolution_unit() -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c1 = cases["QC-V1-01"]
    reg = _registry(_entry("vendor/m:free"))
    provider = MockProvider()
    gateway = Gateway(
        registry=reg,
        providers={"openrouter": provider},
        health=HealthTracker(),
        clock=lambda: FIXED_NOW,
    )
    turn_1 = c1["turns"][0]
    turn_2 = c1["turns"][1]
    history = [
        {"role": turn_1["user_input"] and "user", "content": turn_1["user_input"]},
        {"role": "assistant", "content": turn_1["mock_response"]},
    ]
    result = gateway.generate(
        plan=SYNTHETIC_POLICIES["ananta"],
        text=turn_2["user_input"],
        task_type=TaskType.STUDY,
        max_output_tokens=100,
        history=history,
    )
    assert not result.failed
    assert len(provider.requests) == 1
    sent_msgs = provider.requests[0].messages
    assert len(sent_msgs) == 4
    assert sent_msgs[1]["content"] == turn_1["user_input"]
    assert sent_msgs[2]["content"] == turn_1["mock_response"]
    assert sent_msgs[3]["content"] == turn_2["user_input"]


def test_harness_long_hindi_trim_history_unit() -> None:
    cases = {c["case_id"]: c for c in load_corpus_v1()}
    c3 = cases["QC-V1-03"]
    t1_user = c3["turns"][0]["user_input"]
    t1_resp = c3["turns"][0]["mock_response"]
    t2_user = c3["turns"][1]["user_input"]

    plan = SYNTHETIC_POLICIES["ananta"]
    turns = [
        HistoryTurn(role="user", content=t1_user),
        HistoryTurn(role="assistant", content=t1_resp),
    ]
    trimmed = trim_history(turns, text=t2_user, plan=plan)
    assert len(trimmed) == 2
    assert trimmed[0].content == t1_user
    assert trimmed[1].content == t1_resp


def test_live_runner_budget_hard_stops_at_n_with_mock_adapter(tmp_path: Path) -> None:
    reg = _registry(_entry("vendor/m:free"))
    provider = MockProvider()
    gateway = Gateway(
        registry=reg,
        providers={"openrouter": provider},
        health=HealthTracker(),
        clock=lambda: FIXED_NOW,
    )
    # Total cases and turns exceed budget 2; runner must hard-stop at exactly 2 requests
    results = run_corpus_live(
        budget=2,
        gateway=gateway,
        results_dir=tmp_path / "results",
    )
    assert len(results) == 2
    assert len(provider.requests) == 2
    assert (tmp_path / "results").exists()
    run_files = list((tmp_path / "results").glob("live_run_*.json"))
    assert len(run_files) == 1
    saved_records = json.loads(run_files[0].read_text(encoding="utf-8"))
    assert len(saved_records) == 2
    assert saved_records[0]["case_id"] == "QC-V1-01"
