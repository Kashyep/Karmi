"""Versioned quality corpus and evaluation harness for Karmi multi-turn dialogs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CORPUS_V1_DIR = Path(__file__).resolve().parent / "v1"


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
