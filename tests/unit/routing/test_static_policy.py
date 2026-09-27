"""Unit tests for static routing policy and baseline parity (ADR-0003)."""

from __future__ import annotations

import uuid

import pytest

from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.routing.eligibility import filter_eligible
from daily_agent.routing.features import build_routing_context
from daily_agent.routing.models import TIERS, ModelCandidate, PolicyError
from daily_agent.routing.registry import (
    LIVE_ROUTE,
    LOCAL_ROUTE,
    ProviderHealth,
    model_candidates,
)
from daily_agent.routing.static_policy import (
    STATIC_POLICY_VERSION,
    StaticRoutingPolicy,
)


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("live_enabled", [True, False])
@pytest.mark.parametrize("live_healthy", [True, False])
def test_static_parity_table(tier: str, live_enabled: bool, live_healthy: bool) -> None:
    """Parity: (live enabled × live healthy × tier) -> expected baseline route."""
    health = ProviderHealth(failure_threshold=1, cooldown_seconds=60.0)
    if not live_healthy:
        health.record_failure("typesafe")

    candidates = model_candidates(health)
    ctx = build_routing_context(
        request_id="req-parity",
        run_id="run-parity",
        text="A normal bounded query",
        tier=tier,
        context_budget_tokens=200,
    )
    elig = filter_eligible(
        ctx,
        candidates,
        plan=SYNTHETIC_POLICIES[tier],
        disabled_models=(),
        live_models_enabled=live_enabled,
    )
    policy = StaticRoutingPolicy()
    decision = policy.select(ctx, elig.eligible)

    # If live is enabled and healthy, it should select LIVE_ROUTE (typesafe-system-one).
    # Otherwise, it falls back to LOCAL_ROUTE (fake-economy).
    if live_enabled and live_healthy:
        assert decision.selected_model == LIVE_ROUTE
        assert decision.selected_provider == "typesafe"
    else:
        assert decision.selected_model == LOCAL_ROUTE
        assert decision.selected_provider == "local"

    # Invariants
    assert decision.policy_version == STATIC_POLICY_VERSION
    assert decision.selection_probability == 1.0
    assert not decision.exploration
    assert decision.algorithm == "static"
    uuid.UUID(decision.decision_id)  # must be valid UUID
    assert decision.eligible_models == elig.eligible_models
    assert len(decision.action_probabilities) == len(elig.eligible)

    for model, prob in decision.action_probabilities:
        if model == decision.selected_model:
            assert prob == 1.0
        else:
            assert prob == 0.0


def test_static_custom_preference_and_fallback() -> None:
    cand_a = ModelCandidate(
        provider="p-a",
        model="model-alpha",
        model_version=None,
        max_context_tokens=1000,
        supports_tools=False,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
    )
    cand_b = ModelCandidate(
        provider="p-b",
        model="model-beta",
        model_version=None,
        max_context_tokens=1000,
        supports_tools=False,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
    )
    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )

    # Preference selects model-beta
    policy_beta = StaticRoutingPolicy(preference=("model-beta", "model-alpha"))
    dec = policy_beta.select(ctx, [cand_a, cand_b])
    assert dec.selected_model == "model-beta"

    # Preference selects model-alpha
    policy_alpha = StaticRoutingPolicy(preference=("model-alpha", "model-beta"))
    dec = policy_alpha.select(ctx, [cand_a, cand_b])
    assert dec.selected_model == "model-alpha"

    # No preferred model present -> falls back to smallest model id lexicographically
    policy_other = StaticRoutingPolicy(preference=("model-gamma",))
    dec = policy_other.select(ctx, [cand_b, cand_a])  # cand_b first in list
    assert dec.selected_model == "model-alpha"  # 'model-alpha' < 'model-beta'


def test_static_policy_empty_candidates_raises_policy_error() -> None:
    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )
    policy = StaticRoutingPolicy()
    with pytest.raises(PolicyError, match="candidates must not be empty"):
        policy.select(ctx, [])
