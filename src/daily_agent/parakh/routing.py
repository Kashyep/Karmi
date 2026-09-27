"""Routing evidence for the Parakh optimization loop (producer side of TelemetryBatchV1).

Karmi's live router is static: every request executes exactly one route, chosen
deterministically, so the logged propensity of the executed action is 1.0 and no
exploration happens. Parakh's off-policy evaluation therefore reports zero support
for alternative actions until Karmi runs a separately authorized exploration policy.

A loaded Parakh PolicyBundleV1 in SHADOW state only *records* what it would have
chosen; it never changes the executed route (see ``daily_agent.parakh.receiver``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from daily_agent import __version__
from daily_agent.config import Settings
from daily_agent.models import RoutingDecision, RoutingRecord
from daily_agent.plans import PlanPolicy
from daily_agent.providers import TYPESAFE_INPUT_MICRO_PER_1K, TYPESAFE_OUTPUT_MICRO_PER_1K
from daily_agent.services import (
    LOCAL_FAKE_COST_MICRO,
    ContextManifest,
    GenerationResult,
    measured_cost_micro,
)

logger = logging.getLogger(__name__)

# Parakh's routing-features.v1 (model_lab/optimization/router/features.py). A bundle with a
# different feature schema version is rejected by the receiver.
FEATURE_SCHEMA_VERSION = "routing-features.v1"
STATIC_POLICY_VERSION = "karmi-static-v1"
HARNESS_VERSION = f"karmi-{__version__}"
# Bump when the provider prompt text in daily_agent/providers.py changes.
PROMPT_VERSION = "karmi-prompts-v1"

LOCAL_ACTION = "karmi/fake-economy"
LIVE_ACTION = "typesafe/system-one"
ROUTE_ACTIONS = {"fake-economy": LOCAL_ACTION, "typesafe-system-one": LIVE_ACTION}
KNOWN_ACTIONS = (LOCAL_ACTION, LIVE_ACTION)

# Karmi plan ids -> the TelemetryBatchV1 tier vocabulary Parakh's feature schema one-hots.
# Karmi spells the premium plan "parth"; the contract spells it "part". Unknown plans fail
# closed instead of silently landing in Parakh's "tier=other" feature.
CONTRACT_TIERS = {"ananta": "ananta", "yanta": "yanta", "trika": "trika", "parth": "part"}

# Karmi intents -> Parakh's 15-domain taxonomy (model_lab/schemas.py DOMAINS).
INTENT_DOMAINS = {
    "query_memory": "conversation_memory",
    "store_memory": "conversation_memory",
    "create_task": "task_planning",
    "general_draft": "communication",
}

# Largest working-input cap Karmi enforces on any plan (plans.py); Karmi never sends more.
KARMI_MAX_INPUT_TOKENS = 32_000


class UnknownPlanError(ValueError):
    """The plan has no TelemetryBatchV1 tier mapping."""


def contract_tier(plan_id: str) -> str:
    try:
        return CONTRACT_TIERS[plan_id]
    except KeyError:
        raise UnknownPlanError(f"plan {plan_id!r} has no TelemetryBatchV1 tier") from None


def task_domain(text: str, intent: str | None) -> str:
    """Domain from the classified intent, else the same heuristics ``fake_generate`` uses."""
    if intent in INTENT_DOMAINS:
        return INTENT_DOMAINS[intent]
    lowered = text.casefold()
    if "my notes" in lowered or "remember" in lowered:
        return "conversation_memory"
    return "communication"


def eligible_actions(settings: Settings) -> list[str]:
    """Actions this Karmi process can actually execute for a request."""
    return sorted([LOCAL_ACTION, LIVE_ACTION] if settings.live_models_enabled else [LOCAL_ACTION])


def model_registry() -> list[dict[str, Any]]:
    """TelemetryBatchV1 model registry. Costs are Karmi's synthetic micro-unit rate card / 1e6;
    Karmi has no approved currency, so exported costs carry ISO 4217 test currency ``XTS``."""
    return [
        {
            "provider": "karmi", "model": "fake-economy", "model_version": "local-deterministic",
            "max_context_tokens": KARMI_MAX_INPUT_TOKENS, "supports_tools": False,
            "supports_structured_output": False,
            "estimated_input_cost_per_token": 0.0, "estimated_output_cost_per_token": 0.0,
        },
        {
            "provider": "typesafe", "model": "system-one", "model_version": None,
            "max_context_tokens": KARMI_MAX_INPUT_TOKENS, "supports_tools": False,
            "supports_structured_output": True,
            "estimated_input_cost_per_token": TYPESAFE_INPUT_MICRO_PER_1K / 1000 / 1_000_000,
            "estimated_output_cost_per_token": TYPESAFE_OUTPUT_MICRO_PER_1K / 1000 / 1_000_000,
        },
    ]


def routing_context(
    *, plan: PlanPolicy, text: str, context: ContextManifest, intent: str | None
) -> dict[str, Any]:
    """The RoutingContext Parakh's feature schema interprets. Features only, never text."""
    estimated = context.estimated_tokens + max(1, len(text.encode("utf-8")) // 4)
    return {
        "tier": contract_tier(plan.plan_id),
        "task_domain": task_domain(text, intent),
        "estimated_input_tokens": estimated,
        "context_utilization_ratio": round(min(1.0, estimated / plan.input_tokens), 6),
        "tool_count": 0,
        "requires_structured_output": False,
        "requires_tools": False,
        "requires_memory": bool(context.source_ids),
        "requires_external_data": False,
        # Karmi messages are single-turn with no retry loop at the run level.
        "conversation_depth": 0,
        "retry_number": 0,
        "previous_tool_failure": False,
        "latency_slo_ms": None,
    }


@dataclass(frozen=True)
class RunTiming:
    started_at: datetime
    completed_at: datetime
    latency_ms: float


def _attempts(context: ContextManifest, result: GenerationResult) -> list[dict[str, Any]]:
    calls = [*context.provider_calls, *result.provider_calls]
    if not calls:
        provider, model = LOCAL_ACTION.split("/", 1)
        return [{
            "provider": provider, "model": model, "operation": "generate",
            "input_tokens": None, "output_tokens": None,
            "cost_micro": LOCAL_FAKE_COST_MICRO, "measurement": "fixed",
        }]
    return [
        {
            "provider": call.provider, "model": call.model_id, "operation": call.operation,
            "input_tokens": call.input_tokens, "output_tokens": call.output_tokens,
            "cost_micro": call.cost_micro, "measurement": call.measurement,
        }
        for call in calls
    ]


def record_routing_evidence(
    session: Session,
    *,
    run_id: str,
    settings: Settings,
    plan: PlanPolicy,
    text: str,
    context: ContextManifest,
    result: GenerationResult,
    timing: RunTiming,
) -> dict[str, Any]:
    """Persist the run's routing record, its live decision and (if any) a shadow decision.

    Runs inside the request transaction. Returns the routing context for callers/tests.
    """
    ctx = routing_context(plan=plan, text=text, context=context, intent=result.intent)
    eligible = eligible_actions(settings)
    executed = ROUTE_ACTIONS[result.route]
    session.add(
        RoutingRecord(
            run_id=run_id,
            tier=ctx["tier"],
            task_domain=ctx["task_domain"],
            routing_context=json.dumps(ctx, sort_keys=True),
            attempts=json.dumps(_attempts(context, result), sort_keys=True),
            harness_version=HARNESS_VERSION,
            prompt_version=PROMPT_VERSION,
            policy_version=STATIC_POLICY_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            executed_action=executed,
            latency_ms=timing.latency_ms,
            cost_micro=measured_cost_micro([*context.provider_calls, *result.provider_calls]),
            started_at=timing.started_at,
            completed_at=timing.completed_at,
        )
    )
    session.add(
        RoutingDecision(
            run_id=run_id,
            shadow=False,
            policy_version=STATIC_POLICY_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            selected_action=executed,
            selection_probability=1.0,
            exploration=False,
            eligible_actions=json.dumps(eligible),
            created_at=timing.started_at,
        )
    )
    _record_shadow(session, settings=settings, run_id=run_id, ctx=ctx, eligible=eligible,
                   created_at=timing.started_at)
    session.flush()
    return ctx


def _record_shadow(
    session: Session,
    *,
    settings: Settings,
    run_id: str,
    ctx: dict[str, Any],
    eligible: list[str],
    created_at: datetime,
) -> None:
    """Shadow evaluation is best-effort: it can never change or fail the live request."""
    from daily_agent.parakh.receiver import shadow_select

    try:
        decision = shadow_select(session, settings, ctx, eligible, seed=run_id)
    except Exception:  # a broken candidate must never affect live traffic
        logger.warning("shadow policy evaluation failed; live route unaffected", exc_info=True)
        return
    if decision is None:
        return
    session.add(
        RoutingDecision(
            run_id=run_id,
            shadow=True,
            policy_version=decision["policy_version"],
            feature_schema_version=decision["feature_schema_version"],
            selected_action=decision["selected_action"],
            selection_probability=decision["selection_probability"],
            exploration=decision["exploration"],
            eligible_actions=json.dumps(eligible),
            created_at=created_at,
        )
    )
