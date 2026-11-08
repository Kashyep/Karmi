"""Versioned quality corpus and evaluation harness for Karmi multi-turn dialogs."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from daily_agent.config import Settings
from daily_agent.gateway import Gateway, build_gateway
from daily_agent.gateway.router import classify_task
from daily_agent.plans import SYNTHETIC_POLICIES

CORPUS_V1_DIR = Path(__file__).resolve().parent / "v1"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def load_corpus_v1() -> list[dict[str, Any]]:
    """Load all version 1 quality corpus cases, sorted by case_id."""
    cases: list[dict[str, Any]] = []
    for file_path in sorted(CORPUS_V1_DIR.glob("*.json")):
        if file_path.name == "manifest.json":
            continue
        case = json.loads(file_path.read_text(encoding="utf-8"))
        cases.append(case)
    return cases


def grade_response_quality(prompt: str, response: str) -> dict[str, Any]:
    """Deterministic quality grader for basic defects like verbatim identical echo."""
    stripped_prompt = prompt.strip()
    stripped_response = response.strip()

    if not stripped_response:
        return {
            "status": "fail",
            "reason": "empty_response",
            "evidence": "Response is empty or whitespace only.",
        }

    if stripped_prompt == stripped_response:
        return {
            "status": "fail",
            "reason": "identical_string_echo",
            "evidence": (
                f"Verbatim identical echo defect (2026-10-23): prompt '{stripped_prompt}' "
                f"was echoed identically without assistant assistance."
            ),
        }

    return {
        "status": "pass",
        "reason": "acceptable_non_degenerate",
        "evidence": "Response is non-empty and does not echo user input verbatim.",
    }


def run_corpus_live(
    *,
    budget: int,
    settings: Settings | None = None,
    gateway: Gateway | None = None,
    results_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Run at most ``budget`` corpus turns through the real gateway path.

    Counts provider requests and hard-stops at ``budget``.
    Writes per-case results to tests/quality_corpus/results/.
    """
    if budget <= 0:
        return []

    if gateway is None:
        cfg = settings if settings is not None else Settings()
        if not (cfg.openrouter_enabled and cfg.openrouter_api_key):
            raise ValueError("OpenRouter configuration and API key are required for live evaluation")
        gateway = build_gateway(cfg)

    cases = load_corpus_v1()
    plan = SYNTHETIC_POLICIES["ananta"]
    results: list[dict[str, Any]] = []
    requests_made = 0

    for case in cases:
        if requests_made >= budget:
            break
        case_id = case["case_id"]
        turns = case.get("turns", [])
        if not turns:
            turns = [
                {
                    "turn_index": 1,
                    "user_input": case["messages"][-1]["content"],
                    "history": case["messages"][:-1],
                }
            ]

        for turn in turns:
            if requests_made >= budget:
                break

            user_input = turn["user_input"]
            raw_history = turn.get("history", [])
            history = [{"role": h["role"], "content": h["content"]} for h in raw_history]

            result = gateway.generate(
                plan=plan,
                text=user_input,
                task_type=classify_task(user_input),
                max_output_tokens=plan.output_tokens,
                history=history,
            )
            # Count the provider requests made for this turn (at least 1 attempt)
            calls_count = len(result.calls) if result.calls else 1
            requests_made += calls_count

            answer = result.text or ""
            checks: dict[str, str] = {}

            # 1. Non-degenerate check
            non_deg = grade_response_quality(user_input, answer)
            checks["non_degenerate"] = non_deg["status"]

            # 2. Case-specific automatable checks
            expectations = case.get("harness_expectations", {})
            if expectations.get("is_bad_answer_fixture"):
                checks["bad_answer_avoided"] = "fail" if answer == user_input else "pass"

            if expectations.get("language") == "hi":
                checks["devanagari_present"] = "pass" if _DEVANAGARI.search(answer) else "fail"

            overall_status = "pass" if (not result.failed and all(v == "pass" for v in checks.values())) else "fail"

            record = {
                "case_id": case_id,
                "turn_index": turn.get("turn_index", 1),
                "model_served": result.action,
                "latency_ms": getattr(result, "latency_ms", None),
                "answer": answer,
                "status": overall_status,
                "checks": checks,
            }
            results.append(record)

    out_dir = results_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_file = out_dir / f"live_run_{stamp}.json"
    output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    return results
