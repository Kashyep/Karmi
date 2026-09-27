"""Candidate eligibility filtering (ADR-0003).

Eligibility evaluates hard constraints independently of and before policy execution.
Learned policies select exclusively among eligible routes.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from daily_agent.plans import PlanPolicy
from daily_agent.routing.models import (
    EligibilityResult,
    ModelCandidate,
    NoEligibleModel,
    RoutingContext,
)

REASON_CODES: tuple[str, ...] = (
    "tier_not_entitled",
    "bundle_tier_restriction",
    "model_disabled",
    "live_models_disabled",
    "context_capacity",
    "tools_unsupported",
    "structured_output_unsupported",
    "provider_unhealthy",
    "provider_spend_unverified",
    "request_budget",
    "period_budget",
)


def filter_eligible(
    context: RoutingContext,
    candidates: Sequence[ModelCandidate],
    *,
    plan: PlanPolicy,
    disabled_models: Collection[str],
    live_models_enabled: bool,
    tier_restrictions: Mapping[str, Collection[str]] | None = None,
) -> EligibilityResult:
    """Filter candidate models against hard constraints.

    Collects all failing reason codes per candidate into ``rejections`` as sorted tuples.
    Eligible candidates preserve input order.
    """
    eligible: list[ModelCandidate] = []
    rejections: dict[str, tuple[str, ...]] = {}

    total_tokens = context.estimated_input_tokens + context.context_budget_tokens

    for candidate in candidates:
        reasons: list[str] = []

        if context.tier not in candidate.entitled_tiers:
            reasons.append("tier_not_entitled")

        if (
            tier_restrictions is not None
            and candidate.model in tier_restrictions
            and context.tier not in tier_restrictions[candidate.model]
        ):
            reasons.append("bundle_tier_restriction")

        if candidate.model in disabled_models:
            reasons.append("model_disabled")

        if candidate.requires_live_models and not live_models_enabled:
            reasons.append("live_models_disabled")

        if total_tokens > candidate.max_context_tokens:
            reasons.append("context_capacity")

        if context.requires_tools and not candidate.supports_tools:
            reasons.append("tools_unsupported")

        if context.requires_structured_output and not candidate.supports_structured_output:
            reasons.append("structured_output_unsupported")

        if not candidate.provider_healthy:
            reasons.append("provider_unhealthy")
        if not candidate.spend_bounds_verified:
            reasons.append("provider_spend_unverified")

        expected_cost = candidate.expected_cost_micro(total_tokens)
        if expected_cost > plan.request_cost_cap_micro:
            reasons.append("request_budget")
        if expected_cost > plan.period_cost_cap_micro:
            reasons.append("period_budget")

        if reasons:
            rejections[candidate.model] = tuple(sorted(reasons))
        else:
            eligible.append(candidate)

    return EligibilityResult(eligible=tuple(eligible), rejections=rejections)


def require_eligible(result: EligibilityResult) -> EligibilityResult:
    """Raise NoEligibleModel if no candidate survived eligibility filtering."""
    if not result.eligible:
        raise NoEligibleModel(result.rejections)
    return result
