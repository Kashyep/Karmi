"""Unit tests for shadow routing policy and exception isolation (ADR-0003)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from daily_agent.routing.features import build_routing_context
from daily_agent.routing.models import (
    ModelCandidate,
    PolicyError,
    RoutingContext,
    RoutingDecision,
)
from daily_agent.routing.shadow_policy import ShadowRoutingPolicy
from daily_agent.routing.static_policy import StaticRoutingPolicy


class _FailingPolicy:
    def __init__(self, exc: Exception, version: str = "failing-v1") -> None:
        self._exc = exc
        self._version = version

    @property
    def policy_version(self) -> str:
        return self._version

    def select(
        self,
        context: RoutingContext,
        candidates: Sequence[ModelCandidate],
    ) -> RoutingDecision:
        raise self._exc


def _make_candidate(model: str) -> ModelCandidate:
    return ModelCandidate(
        provider="test-p",
        model=model,
        model_version=None,
        max_context_tokens=10000,
        supports_tools=True,
        supports_structured_output=True,
        estimated_input_cost_per_token=0.0,
        estimated_output_cost_per_token=0.0,
        provider_healthy=True,
    )


def test_shadow_policy_both_succeed() -> None:
    live = StaticRoutingPolicy(preference=("live-model",))
    shadow = StaticRoutingPolicy(preference=("shadow-model",))
    cand_live = _make_candidate("live-model")
    cand_shadow = _make_candidate("shadow-model")
    candidates = [cand_live, cand_shadow]

    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )

    combined = ShadowRoutingPolicy(live=live, shadow=shadow)
    assert combined.policy_version == live.policy_version

    # select() returns live decision
    dec = combined.select(ctx, candidates)
    assert dec.selected_model == "live-model"

    # select_both() returns both decisions and None error
    live_dec, shadow_dec, shadow_err = combined.select_both(ctx, candidates)
    assert live_dec.selected_model == "live-model"
    assert shadow_dec is not None
    assert shadow_dec.selected_model == "shadow-model"
    assert shadow_err is None


@pytest.mark.parametrize(
    ("exc", "expected_err"),
    [
        (PolicyError("shadow failed"), "shadow_PolicyError"),
        (ValueError("bad value"), "shadow_ValueError"),
        (ZeroDivisionError("zero division"), "shadow_ZeroDivisionError"),
        (KeyError("missing key"), "shadow_KeyError"),
        (RuntimeError("runtime issue"), "shadow_RuntimeError"),
    ],
)
def test_shadow_exception_isolation(exc: Exception, expected_err: str) -> None:
    live = StaticRoutingPolicy(preference=("live-model",))
    shadow = _FailingPolicy(exc)
    cand = _make_candidate("live-model")

    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )

    combined = ShadowRoutingPolicy(live=live, shadow=shadow)

    # Live select() is completely unaffected
    live_dec = combined.select(ctx, [cand])
    assert live_dec.selected_model == "live-model"

    # select_both() isolates the shadow exception
    live_dec2, shadow_dec, shadow_err = combined.select_both(ctx, [cand])
    assert live_dec2.selected_model == "live-model"
    assert shadow_dec is None
    assert shadow_err == expected_err


def test_live_exception_propagates() -> None:
    live = _FailingPolicy(PolicyError("live broke"), version="live-v1")
    shadow = StaticRoutingPolicy(preference=("shadow-model",))
    cand = _make_candidate("shadow-model")

    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )

    combined = ShadowRoutingPolicy(live=live, shadow=shadow)

    with pytest.raises(PolicyError, match="live broke"):
        combined.select(ctx, [cand])

    with pytest.raises(PolicyError, match="live broke"):
        combined.select_both(ctx, [cand])
