"""Unit tests for candidate eligibility filtering (ADR-0003)."""

from __future__ import annotations

import pytest

from daily_agent.plans import SYNTHETIC_POLICIES, PlanPolicy
from daily_agent.routing.eligibility import (
    REASON_CODES,
    filter_eligible,
    require_eligible,
)
from daily_agent.routing.features import build_routing_context
from daily_agent.routing.models import (
    ModelCandidate,
    NoEligibleModel,
    RoutingContext,
)
from daily_agent.routing.registry import (
    LIVE_ROUTE,
    LOCAL_ROUTE,
    ProviderHealth,
    model_candidates,
)


def _base_context(
    *,
    tier: str = "ananta",
    text: str = "hello world",
    context_budget_tokens: int = 100,
) -> RoutingContext:
    return build_routing_context(
        request_id="req-elig-1",
        run_id="run-elig-1",
        text=text,
        tier=tier,
        context_budget_tokens=context_budget_tokens,
    )


def test_reason_codes_tuple_complete() -> None:
    expected = (
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
    assert expected == REASON_CODES


def test_reason_code_tier_not_entitled() -> None:
    candidate = ModelCandidate(
        provider="test",
        model="exclusive-part",
        model_version="v1",
        max_context_tokens=10000,
        supports_tools=True,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
        entitled_tiers=frozenset({"part"}),
    )
    ctx = _base_context(tier="ananta")
    result = filter_eligible(
        ctx,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert not result.eligible
    assert result.rejections["exclusive-part"] == ("tier_not_entitled",)


def test_reason_code_bundle_tier_restriction_narrowing_only() -> None:
    candidate = ModelCandidate(
        provider="test",
        model="shared-model",
        model_version="v1",
        max_context_tokens=10000,
        supports_tools=True,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
        entitled_tiers=frozenset({"ananta", "yanta", "trika", "part"}),
    )
    # Narrowing: restrict shared-model to yanta and trika
    restrictions = {"shared-model": ["yanta", "trika"]}

    # Context in ananta -> rejected
    ctx_ananta = _base_context(tier="ananta")
    result_ananta = filter_eligible(
        ctx_ananta,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
        tier_restrictions=restrictions,
    )
    assert not result_ananta.eligible
    assert result_ananta.rejections["shared-model"] == ("bundle_tier_restriction",)

    # Context in yanta -> permitted
    ctx_yanta = _base_context(tier="yanta")
    result_yanta = filter_eligible(
        ctx_yanta,
        [candidate],
        plan=SYNTHETIC_POLICIES["yanta"],
        disabled_models=(),
        live_models_enabled=True,
        tier_restrictions=restrictions,
    )
    assert len(result_yanta.eligible) == 1
    assert result_yanta.eligible[0].model == "shared-model"

    # Model not in tier_restrictions -> not narrowed
    result_no_rest = filter_eligible(
        ctx_ananta,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
        tier_restrictions={"other-model": ["trika"]},
    )
    assert len(result_no_rest.eligible) == 1


def test_reason_code_model_disabled() -> None:
    candidates = model_candidates()
    ctx = _base_context(tier="ananta")
    result = filter_eligible(
        ctx,
        candidates,
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(LOCAL_ROUTE,),
        live_models_enabled=True,
    )
    assert LOCAL_ROUTE not in result.eligible_models
    assert "model_disabled" in result.rejections[LOCAL_ROUTE]


def test_reason_code_live_models_disabled() -> None:
    candidates = model_candidates()
    ctx = _base_context(tier="ananta")
    result = filter_eligible(
        ctx,
        candidates,
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=False,
    )
    assert LIVE_ROUTE not in result.eligible_models
    assert result.rejections[LIVE_ROUTE] == (
        "live_models_disabled",
        "provider_spend_unverified",
    )
    assert LOCAL_ROUTE in result.eligible_models

def test_unverified_provider_spend_rejects_live_route_even_when_enabled() -> None:
    result = filter_eligible(
        _base_context(tier="part"),
        model_candidates(),
        plan=SYNTHETIC_POLICIES["part"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert result.eligible_models == (LOCAL_ROUTE,)
    assert result.rejections[LIVE_ROUTE] == ("provider_spend_unverified",)


def test_reason_code_context_capacity() -> None:
    candidate = ModelCandidate(
        provider="test",
        model="tiny-context",
        model_version="v1",
        max_context_tokens=50,  # small context
        supports_tools=True,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
    )
    # text is ~10 tokens + 100 context budget = 110 > 50
    ctx = _base_context(text="a" * 40, context_budget_tokens=100)
    result = filter_eligible(
        ctx,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert not result.eligible
    assert result.rejections["tiny-context"] == ("context_capacity",)


def test_reason_code_tools_unsupported() -> None:
    candidate = ModelCandidate(
        provider="test",
        model="no-tools",
        model_version="v1",
        max_context_tokens=10000,
        supports_tools=False,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
    )
    base = _base_context()
    # Explicitly set requires_tools
    ctx = RoutingContext(
        request_id=base.request_id,
        run_id=base.run_id,
        tier=base.tier,
        task_domain=base.task_domain,
        estimated_input_tokens=base.estimated_input_tokens,
        context_budget_tokens=base.context_budget_tokens,
        context_utilization_ratio=base.context_utilization_ratio,
        tool_count=1,
        requires_structured_output=False,
        requires_tools=True,
        requires_memory=False,
        requires_external_data=False,
        conversation_depth=0,
        retry_number=0,
        previous_tool_failure=False,
        previous_structured_output_failure=False,
        latency_slo_ms=None,
    )
    result = filter_eligible(
        ctx,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert not result.eligible
    assert result.rejections["no-tools"] == ("tools_unsupported",)


def test_reason_code_structured_output_unsupported() -> None:
    candidate = ModelCandidate(
        provider="test",
        model="no-structured",
        model_version="v1",
        max_context_tokens=10000,
        supports_tools=True,
        supports_structured_output=False,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
    )
    base = _base_context()
    ctx = RoutingContext(
        request_id=base.request_id,
        run_id=base.run_id,
        tier=base.tier,
        task_domain=base.task_domain,
        estimated_input_tokens=base.estimated_input_tokens,
        context_budget_tokens=base.context_budget_tokens,
        context_utilization_ratio=base.context_utilization_ratio,
        tool_count=0,
        requires_structured_output=True,
        requires_tools=False,
        requires_memory=False,
        requires_external_data=False,
        conversation_depth=0,
        retry_number=0,
        previous_tool_failure=False,
        previous_structured_output_failure=False,
        latency_slo_ms=None,
    )
    result = filter_eligible(
        ctx,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert not result.eligible
    assert result.rejections["no-structured"] == ("structured_output_unsupported",)


def test_reason_code_provider_unhealthy() -> None:
    health = ProviderHealth(failure_threshold=2, cooldown_seconds=60.0)
    health.record_failure("typesafe")
    health.record_failure("typesafe")
    assert not health.is_healthy("typesafe")

    candidates = model_candidates(health)
    ctx = _base_context(tier="ananta")
    result = filter_eligible(
        ctx,
        candidates,
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert LIVE_ROUTE not in result.eligible_models
    assert result.rejections[LIVE_ROUTE] == (
        "provider_spend_unverified",
        "provider_unhealthy",
    )
    assert LOCAL_ROUTE in result.eligible_models


def test_reason_codes_cost_budgets() -> None:
    # Candidate with high cost
    candidate = ModelCandidate(
        provider="test",
        model="expensive-model",
        model_version="v1",
        max_context_tokens=10000,
        supports_tools=True,
        supports_structured_output=True,
        estimated_input_cost_per_token=10.0,
        estimated_output_cost_per_token=10.0,
        provider_healthy=True,
        fixed_cost_micro=3000,  # exceeds request cap of 2000 for ananta
    )
    ctx = _base_context(tier="ananta", context_budget_tokens=100)
    # Ananta request_cost_cap_micro = 2_000, period_cost_cap_micro = 20_000
    result_request = filter_eligible(
        ctx,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    assert not result_request.eligible
    assert result_request.rejections["expensive-model"] == ("request_budget",)

    # Exceeding both request and period budget
    tight_plan = PlanPolicy(
        plan_id="tight",
        display_name="Tight",
        everyday_limit=1,
        input_tokens=100,
        output_tokens=100,
        request_cost_cap_micro=1000,
        period_cost_cap_micro=2000,
        allowed_routes=("expensive-model",),
    )
    result_both = filter_eligible(
        ctx,
        [candidate],
        plan=tight_plan,
        disabled_models=(),
        live_models_enabled=True,
    )
    assert not result_both.eligible
    assert result_both.rejections["expensive-model"] == ("period_budget", "request_budget")


def test_multiple_reasons_collected_and_sorted() -> None:
    candidate = ModelCandidate(
        provider="test",
        model="multi-fail",
        model_version="v1",
        max_context_tokens=10,  # context capacity
        supports_tools=False,
        supports_structured_output=False,
        estimated_input_cost_per_token=100.0,
        estimated_output_cost_per_token=100.0,
        provider_healthy=False,  # provider unhealthy
        fixed_cost_micro=50000,  # request + period budget
        requires_live_models=True,  # live models disabled
        entitled_tiers=frozenset({"part"}),  # tier not entitled
    )
    ctx = _base_context(tier="ananta", context_budget_tokens=100)
    result = filter_eligible(
        ctx,
        [candidate],
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=("multi-fail",),  # model disabled
        live_models_enabled=False,
    )
    reasons = result.rejections["multi-fail"]
    # Check all failing reasons were collected
    expected_reasons = {
        "tier_not_entitled",
        "model_disabled",
        "live_models_disabled",
        "context_capacity",
        "provider_unhealthy",
        "request_budget",
        "period_budget",
    }
    assert set(reasons) == expected_reasons
    # Must be sorted alphabetically
    assert reasons == tuple(sorted(reasons))


def test_require_eligible() -> None:
    candidates = model_candidates()
    ctx = _base_context(tier="ananta")
    result = filter_eligible(
        ctx,
        candidates,
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(),
        live_models_enabled=True,
    )
    # Successful require_eligible
    passed = require_eligible(result)
    assert passed is result

    # When none are eligible
    empty_result = filter_eligible(
        ctx,
        candidates,
        plan=SYNTHETIC_POLICIES["ananta"],
        disabled_models=(LOCAL_ROUTE, LIVE_ROUTE),
        live_models_enabled=True,
    )
    with pytest.raises(NoEligibleModel) as exc_info:
        require_eligible(empty_result)
    assert exc_info.value.rejections == empty_result.rejections
