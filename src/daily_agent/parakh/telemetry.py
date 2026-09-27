"""Export sanitized routing evidence as a Parakh TelemetryBatchV1 document.

Only whitelisted routing features, decisions and measured metrics leave Karmi: never
message or response text, note content, account/user ids or client idempotency keys.
Exports are deterministic for a window: the batch id is derived from the window and
content, and ``generated_at`` is the window end, so re-exporting an unchanged window
yields byte-identical JSON that Parakh imports idempotently. Late-arriving runs change
the content and therefore the batch id instead of conflicting with an earlier import.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent import __version__
from daily_agent.models import RoutingDecision, RoutingRecord, Run, RunStatus
from daily_agent.parakh.routing import FEATURE_SCHEMA_VERSION, model_registry

SCHEMA_VERSION = "1.0"
PRODUCER_REPO = "Kashyep/Karmi"
# Karmi's money columns are synthetic micro-units with no approved currency (ISO 4217 "XTS"
# is reserved for testing). Parakh deliberately does not normalize non-USD cost.
COST_CURRENCY = "XTS"


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _money(micro: int | None) -> float | None:
    return None if micro is None else micro / 1_000_000


def _ref(prefix: str, row_id: str) -> str:
    """Stable export id for a Karmi UUID. Dashed UUID groups can be 12 bare digits, which
    Parakh's privacy scan correctly treats as a possible Aadhaar number and quarantines;
    a prefixed undashed hex token never forms an isolated digit run."""
    return f"{prefix}-{uuid.UUID(row_id).hex}"


def _decision(decision: RoutingDecision) -> dict[str, Any]:
    provider, model = decision.selected_action.split("/", 1)
    return {
        "decision_id": _ref("dec", decision.id),
        "selected_provider": provider,
        "selected_model": model,
        "policy_version": decision.policy_version,
        "selection_probability": decision.selection_probability,
        "exploration": decision.exploration,
        "shadow": decision.shadow,
        "eligible_models": json.loads(decision.eligible_actions),
        "feature_schema_version": decision.feature_schema_version,
        "created_at": _iso(decision.created_at),
    }


def _run(record: RoutingRecord, run: Run, decisions: list[RoutingDecision]) -> dict[str, Any]:
    live = next(d for d in decisions if not d.shadow)
    attempts = [
        {
            "attempt_id": f"{_ref('att', run.id)}-{index}",
            "decision_id": _ref("dec", live.id),
            "provider": attempt["provider"],
            "model": attempt["model"],
            "operation": attempt["operation"],
            "success": True,
            "retry_number": 0,
            "input_tokens": attempt["input_tokens"],
            "output_tokens": attempt["output_tokens"],
            "estimated_cost": _money(attempt["cost_micro"]),
            "currency": COST_CURRENCY if attempt["cost_micro"] is not None else None,
            "cost_measurement": attempt["measurement"],
            "latency_ms": None,
            "error_type": None,
        }
        for index, attempt in enumerate(json.loads(record.attempts))
    ]
    completed = run.status == RunStatus.COMPLETED
    request_digest = hashlib.sha256(f"{run.account_id}:{run.logical_request_id}".encode())
    return {
        "run_id": _ref("run", run.id),
        "request_id": f"req-{request_digest.hexdigest()[:24]}",
        "session_id_hash": None,
        "started_at": _iso(record.started_at),
        "completed_at": _iso(record.completed_at),
        "task_domain": record.task_domain,
        "tier": record.tier,
        "harness_version": record.harness_version,
        "prompt_version": record.prompt_version,
        "policy_version": record.policy_version,
        "feature_schema_version": record.feature_schema_version,
        "status": run.status,
        "karmi_outcome": run.outcome,
        "routing_context": json.loads(record.routing_context),
        "decisions": [_decision(d) for d in decisions],
        "attempts": attempts,
        "tool_events": [],
        "validation_events": [],
        "outcome": {
            "completed": completed,
            # Karmi runs have no run-level retry, so the first attempt is the only attempt.
            "first_shot_success": completed,
            "structured_output_valid": None,
            "tool_success": None,
            "retry_count": 0,
            "user_retry_signal": None,
            "user_abandon_signal": None,
            "user_accept_signal": None,
            "user_correction_signal": None,
            "correction_distance": None,
            "final_latency_ms": record.latency_ms,
            "final_cost": _money(record.cost_micro),
            "currency": COST_CURRENCY if record.cost_micro is not None else None,
            "finalized_at": _iso(record.completed_at),
            "critical_failure": None,
        },
        "feedback": [],
    }


def build_telemetry_batch(session: Session, *, start: datetime, end: datetime) -> dict[str, Any]:
    """TelemetryBatchV1 for runs whose routing record completed in ``[start, end)``."""
    if end <= start:
        raise ValueError("window end must be after its start")
    records = list(
        session.scalars(
            select(RoutingRecord)
            .where(RoutingRecord.completed_at >= start, RoutingRecord.completed_at < end)
            .order_by(RoutingRecord.completed_at, RoutingRecord.run_id)
        )
    )
    run_ids = [record.run_id for record in records]
    runs = {run.id: run for run in session.scalars(select(Run).where(Run.id.in_(run_ids)))}
    decisions: dict[str, list[RoutingDecision]] = {run_id: [] for run_id in run_ids}
    for decision in session.scalars(
        select(RoutingDecision)
        .where(RoutingDecision.run_id.in_(run_ids))
        .order_by(RoutingDecision.run_id, RoutingDecision.shadow, RoutingDecision.policy_version)
    ):
        decisions[decision.run_id].append(decision)
    exported = [_run(record, runs[record.run_id], decisions[record.run_id]) for record in records]
    window = {"start": _iso(start), "end": _iso(end)}
    digest = hashlib.sha256(
        json.dumps({"window": window, "runs": exported}, sort_keys=True).encode()
    ).hexdigest()
    return {
        "schema": "TelemetryBatchV1",
        "schema_version": SCHEMA_VERSION,
        "batch_id": f"karmi-{digest[:24]}",
        "generated_at": window["end"],
        "producer": {"repo": PRODUCER_REPO, "version": __version__},
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "window": window,
        "model_registry": model_registry(),
        "runs": exported,
    }
