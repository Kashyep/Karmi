"""Candidate-only, request-count-bounded OpenCode Zen evaluation runner."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from daily_agent.opencode import (
    FREE_MODEL_BY_ID,
    FREE_RATE_VERSION,
    OpenCodeError,
    chat_completion,
    fetch_catalog,
)
from model_lab.core import candidate_record, prompt_hash, validate_cases


class EvaluationPlanError(ValueError):
    """The candidate run is invalid or exceeds its declared request budget."""


def run_opencode_candidates(
    *,
    cases: list[dict[str, Any]],
    model_ids: list[str],
    split: str,
    max_requests: int,
    api_key: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run synthetic candidate prompts sequentially; failures remain explicit attempts."""
    if errors := validate_cases(cases):
        raise EvaluationPlanError("invalid suite: " + "; ".join(errors[:3]))
    if split not in {"train", "calibration", "holdout", "all"}:
        raise EvaluationPlanError("split must be train, calibration, holdout, or all")
    if not model_ids or len(set(model_ids)) != len(model_ids):
        raise EvaluationPlanError("select at least one unique candidate model")
    if max_requests < 1:
        raise EvaluationPlanError("max_requests must be positive")
    unknown = sorted(set(model_ids) - FREE_MODEL_BY_ID.keys())
    if unknown:
        raise EvaluationPlanError(f"models are outside the dated free allowlist: {unknown}")
    selected_cases = [case for case in cases if split == "all" or case["split"] == split]
    request_count = len(selected_cases) * len(model_ids)
    if request_count == 0:
        raise EvaluationPlanError("the selected split has no cases")
    if not api_key.strip():
        raise EvaluationPlanError("an OpenCode API key is required")
    # The catalog check is also a provider request, so it counts against the cap.
    total_requests = request_count + 1
    if total_requests > max_requests:
        raise EvaluationPlanError(
            f"plan needs {total_requests} requests (including the catalog check), "
            f"exceeding max_requests={max_requests}"
        )

    try:
        available = fetch_catalog(api_key=api_key)
    except OpenCodeError as exc:
        raise EvaluationPlanError(str(exc)) from exc
    missing = sorted(set(model_ids) - available)
    if missing:
        raise EvaluationPlanError(f"selected models are not in the current provider catalog: {missing}")

    run_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()
    attempts: list[dict[str, Any]] = []
    for model_id in model_ids:
        for case in selected_cases:
            candidate = candidate_record(case)
            raw_output_limit = candidate.get("limits", {}).get("max_output_tokens", 512)
            output_limit = (
                min(max(raw_output_limit, 1), 1_024)
                if isinstance(raw_output_limit, int)
                else 512
            )
            # Only messages cross the provider boundary. Evaluation, split, and case metadata
            # remain local even though candidate_record has a local audit hash.
            try:
                completion = chat_completion(
                    api_key=api_key,
                    model_id=model_id,
                    messages=candidate["messages"],
                    max_output_tokens=output_limit,
                )
                attempt = {
                    "attempt_id": f"{run_id}:{model_id}:{case['case_id']}",
                    "case_id": case["case_id"],
                    "model_id": completion.model_id,
                    "response": completion.text,
                    "status": "completed",
                    "prompt_hash": prompt_hash(candidate["messages"]),
                    "latency_ms": round(completion.latency_ms, 3),
                    "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens,
                    "provenance": {
                        "kind": "live_provider",
                        "provider": "opencode-zen",
                        "run_id": run_id,
                        "rate_version": FREE_RATE_VERSION,
                        "created_at": created_at,
                        "finish_reason": completion.finish_reason,
                        "cost_micro": completion.cost_micro,
                        "cost_measurement": "dated-free-catalog",
                        "max_requests": max_requests,
                        "split": split,
                    },
                }
            except OpenCodeError:
                attempt = {
                    "attempt_id": f"{run_id}:{model_id}:{case['case_id']}",
                    "case_id": case["case_id"],
                    "model_id": model_id,
                    "response": "",
                    "status": "failed",
                    "prompt_hash": prompt_hash(candidate["messages"]),
                    "latency_ms": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "provenance": {
                        "kind": "live_provider",
                        "provider": "opencode-zen",
                        "run_id": run_id,
                        "rate_version": FREE_RATE_VERSION,
                        "created_at": created_at,
                        "error": "provider_request_failed",
                        "cost_micro": None,
                        "cost_measurement": "unknown",
                        "max_requests": max_requests,
                        "split": split,
                    },
                }
            attempts.append(attempt)

    manifest = {
        "run_id": run_id,
        "created_at": created_at,
        "provider": "opencode-zen",
        "rate_version": FREE_RATE_VERSION,
        "split": split,
        "candidate_models": model_ids,
        "case_count_per_model": len(selected_cases),
        "planned_requests": request_count,
        "max_requests": max_requests,
        "sequence": "sequential-no-retries",
        "candidate_data": "messages-only; synthetic benchmark prompts",
        "selection_claim": "none; this run is evidence input, not a router decision",
    }
    return manifest, attempts
