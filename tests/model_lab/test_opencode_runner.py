"""Offline tests for the bounded OpenCode candidate runner and its CLI wiring.

Every HTTP request is served by an httpx.MockTransport injected into daily_agent.opencode, so
no test performs a network call. The credential is a synthetic placeholder.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import daily_agent.opencode as opencode_module
from daily_agent.opencode import FREE_MODEL_BY_ID, FREE_MODELS, ZEN_CATALOG_URL, ZEN_CHAT_URL
from model_lab import cli as cli_module
from model_lab.cli import app
from model_lab.core import write_jsonl
from model_lab.opencode_runner import EvaluationPlanError, run_opencode_candidates

SYNTHETIC_KEY = "test-key-synthetic"
ALLOWED_MODEL = "big-pickle"
SECOND_MODEL = "exo-free"
SEED_SUITE = Path(__file__).resolve().parents[2] / "benchmarks" / "seed_cases.jsonl"
REQUEST_BODY_KEYS = {"model", "messages", "max_tokens", "temperature", "stream"}


@dataclass
class FakeZen:
    """Records every request that reaches the mock transport and scripts provider replies."""

    requests: list[httpx.Request] = field(default_factory=list)
    catalog_ids: list[str] = field(
        default_factory=lambda: [model.model_id for model in FREE_MODELS] + ["gpt-unlisted"]
    )
    chat_responder: Callable[[dict[str, Any]], httpx.Response] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET" and str(request.url) == ZEN_CATALOG_URL:
            return httpx.Response(200, json={"data": [{"id": mid} for mid in self.catalog_ids]})
        if request.method == "POST" and str(request.url) == ZEN_CHAT_URL:
            body = json.loads(request.content)
            if self.chat_responder is not None:
                return self.chat_responder(body)
            return _success(body)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def chat_posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST" and str(r.url) == ZEN_CHAT_URL]


def _success(body: dict[str, Any]) -> httpx.Response:
    content = body["messages"][-1]["content"]
    return httpx.Response(
        200,
        json={
            "id": "synthetic-completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": f"ack: {content[:20]}"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        },
    )


@pytest.fixture
def zen(monkeypatch: pytest.MonkeyPatch) -> FakeZen:
    """Route every httpx.Client created by daily_agent.opencode through a mock transport."""
    fake = FakeZen()
    transport = httpx.MockTransport(fake.handle)
    real_client = httpx.Client

    class MockedClient(real_client):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(opencode_module.httpx, "Client", MockedClient)
    return fake


def _case(case_id: str, split: str, content: str) -> dict[str, Any]:
    """A synthetic case whose evaluation block carries sentinel secrets."""
    return {
        "case_id": case_id,
        "family_id": "synthetic-family-v1",
        "split": split,
        "complexity_level": 1,
        "domain": "synthetic",
        "language": "en",
        "tags": ["synthetic"],
        "messages": [
            {"role": "system", "content": "Synthetic system instruction."},
            {"role": "user", "content": content},
        ],
        "evaluation": {
            "method": "rubric",
            "reference_answer": f"SENTINEL-REFERENCE-{case_id}",
            "rubric": [{"criterion": f"SENTINEL-RUBRIC-{case_id}", "weight": 1}],
            "critical_failures": [f"SENTINEL-CRITICAL-{case_id}"],
        },
        "fixture_policy": "synthetic-only",
        "suite_version": "0.0.0-test",
        "provenance": {"origin": "synthetic_authored", "real_personal_data": False},
        "limits": {"max_output_tokens": 64, "max_tool_calls": 0},
    }


def _suite() -> list[dict[str, Any]]:
    return [
        _case("T-01", "train", "Synthetic prompt alpha one."),
        _case("T-02", "calibration", "Synthetic prompt beta two."),
        _case("T-03", "holdout", "Synthetic prompt gamma three."),
    ]


def _write_suite(tmp_path: Path, cases: list[dict[str, Any]]) -> Path:
    path = tmp_path / "suite.jsonl"
    write_jsonl(path, cases)
    return path


def _cli_args(suite: Path, out_dir: Path, *extra: str, max_requests: int = 10) -> list[str]:
    return [
        "run-opencode",
        "--suite",
        str(suite),
        "--out-dir",
        str(out_dir),
        "--max-requests",
        str(max_requests),
        *extra,
    ]


# 1. Live execution must be explicitly enabled and keyed.


def test_cli_refuses_live_run_without_allow_flag(
    zen: FakeZen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli_module, "get_settings", lambda: SimpleNamespace(opencode_api_key=SYNTHETIC_KEY)
    )
    suite = _write_suite(tmp_path, _suite())
    out_dir = tmp_path / "run"

    # CI (GITHUB_ACTIONS) makes rich style the error panel, which splits the option name with
    # escape codes; strip them and widen the terminal so the name stays on one line.
    result = CliRunner().invoke(
        app, _cli_args(suite, out_dir, "--model", ALLOWED_MODEL), env={"COLUMNS": "200"}
    )

    assert result.exit_code == 2
    assert "--allow-free-provider-requests" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert zen.requests == []
    assert not out_dir.exists()


def test_cli_refuses_live_run_without_saved_key(
    zen: FakeZen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli_module, "get_settings", lambda: SimpleNamespace(opencode_api_key=None))
    suite = _write_suite(tmp_path, _suite())
    out_dir = tmp_path / "run"

    result = CliRunner().invoke(
        app,
        _cli_args(suite, out_dir, "--model", ALLOWED_MODEL, "--allow-free-provider-requests"),
    )

    assert result.exit_code == 2
    assert "setup_opencode.py" in result.output
    assert zen.requests == []
    assert not out_dir.exists()


def test_runner_refuses_empty_api_key_before_any_provider_call(zen: FakeZen) -> None:
    with pytest.raises(EvaluationPlanError):
        run_opencode_candidates(
            cases=_suite(),
            model_ids=[ALLOWED_MODEL],
            split="all",
            max_requests=10,
            api_key="",
        )
    assert zen.requests == []


# 2. Model IDs must come from the dated free allowlist.


def test_runner_rejects_models_outside_allowlist_without_requests(zen: FakeZen) -> None:
    catalog_only = "gpt-unlisted"
    assert catalog_only not in FREE_MODEL_BY_ID
    assert catalog_only in zen.catalog_ids

    with pytest.raises(EvaluationPlanError, match="allowlist"):
        run_opencode_candidates(
            cases=_suite(),
            model_ids=[ALLOWED_MODEL, catalog_only],
            split="all",
            max_requests=10,
            api_key=SYNTHETIC_KEY,
        )
    assert zen.requests == []


def test_cli_rejects_model_outside_allowlist(
    zen: FakeZen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli_module, "get_settings", lambda: SimpleNamespace(opencode_api_key=SYNTHETIC_KEY)
    )
    suite = _write_suite(tmp_path, _suite())
    out_dir = tmp_path / "run"

    result = CliRunner().invoke(
        app,
        _cli_args(suite, out_dir, "--model", "gpt-unlisted", "--allow-free-provider-requests"),
    )

    assert result.exit_code == 2
    assert "gpt-unlisted" in result.output
    assert zen.requests == []
    assert not out_dir.exists()


# 3. The explicit request-count cap is enforced.


def test_runner_refuses_plan_exceeding_cap_without_requests(zen: FakeZen) -> None:
    cases = _suite()  # 3 cases
    with pytest.raises(EvaluationPlanError, match="exceeding max_requests=5"):
        run_opencode_candidates(
            cases=cases,
            model_ids=[ALLOWED_MODEL, SECOND_MODEL],  # 6 planned requests
            split="all",
            max_requests=5,
            api_key=SYNTHETIC_KEY,
        )
    assert zen.requests == []


def test_runner_at_cap_makes_no_more_http_requests_than_cap(zen: FakeZen) -> None:
    cases = _suite()
    planned = 3 * 2
    cap = planned + 1  # completions plus the catalog check
    manifest, attempts = run_opencode_candidates(
        cases=cases,
        model_ids=[ALLOWED_MODEL, SECOND_MODEL],
        split="all",
        max_requests=cap,
        api_key=SYNTHETIC_KEY,
    )

    assert manifest["planned_requests"] == planned
    assert len(attempts) == planned
    assert len(zen.chat_posts()) == planned
    # The catalog GET is also a provider HTTP request and must not push past the cap.
    assert len(zen.requests) <= cap


def test_cli_refuses_plan_exceeding_cap_and_writes_nothing(
    zen: FakeZen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli_module, "get_settings", lambda: SimpleNamespace(opencode_api_key=SYNTHETIC_KEY)
    )
    suite = _write_suite(tmp_path, _suite())
    out_dir = tmp_path / "run"

    result = CliRunner().invoke(
        app,
        _cli_args(
            suite,
            out_dir,
            "--model",
            ALLOWED_MODEL,
            "--model",
            SECOND_MODEL,
            "--allow-free-provider-requests",
            max_requests=5,
        ),
    )

    assert result.exit_code == 2
    assert "exceeding max_requests=5" in result.output
    assert zen.requests == []
    assert not out_dir.exists()


# 4. Only synthetic messages cross the provider boundary.


def test_request_bodies_carry_only_messages_and_no_evaluation_or_split_data(zen: FakeZen) -> None:
    cases = _suite()
    run_opencode_candidates(
        cases=cases,
        model_ids=[ALLOWED_MODEL],
        split="all",
        max_requests=10,
        api_key=SYNTHETIC_KEY,
    )

    posts = zen.chat_posts()
    assert len(posts) == len(cases)
    raw_bodies = [request.content.decode("utf-8") for request in posts]
    for raw in raw_bodies:
        for case in cases:
            evaluation = case["evaluation"]
            assert evaluation["reference_answer"] not in raw
            assert evaluation["rubric"][0]["criterion"] not in raw
            assert evaluation["critical_failures"][0] not in raw
            assert case["split"] not in raw
            assert case["provenance"]["origin"] not in raw
        for forbidden_key in ("evaluation", "split", "provenance", "case_id", "limits", "tags"):
            assert f'"{forbidden_key}"' not in raw


def test_request_body_shape_is_fixed_and_messages_match_fixture(zen: FakeZen) -> None:
    cases = _suite()
    run_opencode_candidates(
        cases=cases,
        model_ids=[ALLOWED_MODEL],
        split="all",
        max_requests=10,
        api_key=SYNTHETIC_KEY,
    )

    bodies = [json.loads(request.content) for request in zen.chat_posts()]
    for body, case in zip(bodies, cases, strict=True):
        assert set(body) == REQUEST_BODY_KEYS
        assert body["model"] == ALLOWED_MODEL
        assert body["stream"] is False
        assert body["max_tokens"] == case["limits"]["max_output_tokens"]
        assert body["messages"] == case["messages"]
        assert all(set(message) == {"role", "content"} for message in body["messages"])


def test_seed_suite_requests_leak_no_reference_answers_or_split_labels(zen: FakeZen) -> None:
    from model_lab.core import read_jsonl

    cases = read_jsonl(SEED_SUITE)
    run_opencode_candidates(
        cases=cases,
        model_ids=[ALLOWED_MODEL],
        split="holdout",
        max_requests=len(cases),
        api_key=SYNTHETIC_KEY,
    )

    holdout = [case for case in cases if case["split"] == "holdout"]
    posts = zen.chat_posts()
    assert len(posts) == len(holdout)
    raw_bodies = "\n".join(request.content.decode("utf-8") for request in posts)
    for case in holdout:
        assert case["evaluation"]["reference_answer"] not in raw_bodies
    assert '"holdout"' not in raw_bodies
    assert '"reference_answer"' not in raw_bodies


# 5. Results keep provenance; provider failures stay explicit and are never retried.


def test_completed_attempt_records_model_usage_latency_and_provenance(zen: FakeZen) -> None:
    manifest, attempts = run_opencode_candidates(
        cases=[_case("T-01", "train", "Synthetic prompt alpha one.")],
        model_ids=[ALLOWED_MODEL],
        split="train",
        max_requests=2,
        api_key=SYNTHETIC_KEY,
    )

    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["status"] == "completed"
    assert attempt["case_id"] == "T-01"
    assert attempt["model_id"] == ALLOWED_MODEL
    assert attempt["input_tokens"] == 11
    assert attempt["output_tokens"] == 7
    assert isinstance(attempt["latency_ms"], float)
    assert attempt["latency_ms"] >= 0
    assert attempt["response"].startswith("ack:")
    assert attempt["prompt_hash"]
    provenance = attempt["provenance"]
    assert provenance["kind"] == "live_provider"
    assert provenance["provider"] == "opencode-zen"
    assert provenance["run_id"] == manifest["run_id"]
    assert provenance["rate_version"] == manifest["rate_version"]
    assert provenance["finish_reason"] == "stop"
    assert provenance["cost_micro"] == 0
    assert provenance["cost_measurement"] == "dated-free-catalog"
    assert provenance["split"] == "train"
    assert provenance["max_requests"] == 2
    assert manifest["candidate_data"].startswith("messages-only")
    assert manifest["sequence"] == "sequential-no-retries"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(lambda body: httpx.Response(500, text="boom"), id="http-500"),
        pytest.param(lambda body: httpx.Response(200, content=b"not json"), id="malformed-json"),
        pytest.param(lambda body: httpx.Response(200, json={"choices": []}), id="no-choices"),
        pytest.param(
            lambda body: httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "   "}}]},
            ),
            id="empty-text",
        ),
    ],
)
def test_provider_failure_is_preserved_as_failed_record_with_one_request(
    zen: FakeZen, failure: Callable[[dict[str, Any]], httpx.Response]
) -> None:
    cases = _suite()
    failing_case_id = "T-02"

    def responder(body: dict[str, Any]) -> httpx.Response:
        if body["messages"][-1]["content"] == cases[1]["messages"][-1]["content"]:
            return failure(body)
        return _success(body)

    zen.chat_responder = responder
    manifest, attempts = run_opencode_candidates(
        cases=cases,
        model_ids=[ALLOWED_MODEL],
        split="all",
        max_requests=10,
        api_key=SYNTHETIC_KEY,
    )

    # Exactly one completion request per case: the failure is not retried.
    assert len(zen.chat_posts()) == len(cases)
    assert len(attempts) == len(cases)
    by_case = {attempt["case_id"]: attempt for attempt in attempts}
    failed = by_case[failing_case_id]
    assert failed["status"] == "failed"
    assert failed["model_id"] == ALLOWED_MODEL
    assert failed["response"] == ""
    assert failed["latency_ms"] is None
    assert failed["input_tokens"] is None
    assert failed["output_tokens"] is None
    assert failed["provenance"]["error"] == "provider_request_failed"
    assert failed["provenance"]["cost_measurement"] == "unknown"
    assert failed["provenance"]["cost_micro"] is None
    assert failed["provenance"]["run_id"] == manifest["run_id"]
    for case_id in ("T-01", "T-03"):
        assert by_case[case_id]["status"] == "completed"


def test_cli_writes_failed_attempts_to_output_and_reports_counts(
    zen: FakeZen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli_module, "get_settings", lambda: SimpleNamespace(opencode_api_key=SYNTHETIC_KEY)
    )
    cases = _suite()

    def responder(body: dict[str, Any]) -> httpx.Response:
        if body["messages"][-1]["content"] == cases[0]["messages"][-1]["content"]:
            return httpx.Response(500, text="boom")
        return _success(body)

    zen.chat_responder = responder
    suite = _write_suite(tmp_path, cases)
    out_dir = tmp_path / "run"

    result = CliRunner().invoke(
        app,
        _cli_args(
            suite,
            out_dir,
            "--model",
            ALLOWED_MODEL,
            "--allow-free-provider-requests",
            max_requests=4,
        ),
    )

    assert result.exit_code == 0, result.output
    assert "planned=3 completed=2 failed=1" in result.output
    assert len(zen.chat_posts()) == 3
    lines = (out_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert sorted(row["status"] for row in rows) == ["completed", "completed", "failed"]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["max_requests"] == 4
    assert manifest["planned_requests"] == 3
