"""Unit tests for bandit routing policy and LinUCB scoring (ADR-0003)."""

from __future__ import annotations

import math
import random
import uuid

import pytest

from daily_agent.policy_artifacts.schema import LinUCBArmV1, LinUCBPolicyV1
from daily_agent.routing.bandit_policy import (
    BanditRoutingPolicy,
    ExplorationConfig,
)
from daily_agent.routing.features import build_routing_context
from daily_agent.routing.models import (
    FEATURE_NAMES_V1,
    FEATURE_SCHEMA_VERSION,
    TIERS,
    ModelCandidate,
    PolicyError,
)

DIM = len(FEATURE_NAMES_V1)
class _FixedRng(random.Random):
    def __init__(self, val: float) -> None:
        super().__init__()
        self._val = val

    def random(self) -> float:
        return self._val



def _identity_matrix(dim: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(dim)]


def _make_arm(dim: int, theta_val: float = 0.1) -> LinUCBArmV1:
    return LinUCBArmV1(
        theta=[theta_val] * dim,
        a_inv=_identity_matrix(dim),
    )


def _make_policy(
    arms: dict[str, LinUCBArmV1],
    *,
    alpha: float = 0.5,
    feature_schema_version: str = FEATURE_SCHEMA_VERSION,
) -> LinUCBPolicyV1:
    return LinUCBPolicyV1(
        schema="LinUCBPolicyV1",
        feature_schema_version=feature_schema_version,
        alpha=alpha,
        arms=arms,
    )


def _make_candidate(
    model: str,
    *,
    fixed_cost: int = 100,
    cost_per_token: float = 0.0,
) -> ModelCandidate:
    return ModelCandidate(
        provider="test-provider",
        model=model,
        model_version="v1",
        max_context_tokens=100_000,
        supports_tools=True,
        supports_structured_output=True,
        estimated_input_cost_per_token=cost_per_token,
        estimated_output_cost_per_token=cost_per_token,
        provider_healthy=True,
        fixed_cost_micro=fixed_cost,
    )


def test_constructor_validation() -> None:
    arms = {"m1": _make_arm(DIM)}

    # Invalid feature schema version
    bad_schema = _make_policy(arms, feature_schema_version="invalid-schema-v2")
    with pytest.raises(PolicyError, match="unsupported feature schema version"):
        BanditRoutingPolicy(bad_schema, policy_version="v1")

    # Dimension mismatch
    arm_wrong_dim = LinUCBArmV1(
        theta=[0.1] * 5,
        a_inv=_identity_matrix(5),
    )
    bad_dim = LinUCBPolicyV1(
        schema="LinUCBPolicyV1",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        alpha=0.5,
        arms={"m1": arm_wrong_dim},
    )
    with pytest.raises(PolicyError, match="policy dimension 5 does not match"):
        BanditRoutingPolicy(bad_dim, policy_version="v1")


def test_select_empty_candidates_raises_policy_error() -> None:
    policy_params = _make_policy({"m1": _make_arm(DIM)})
    policy = BanditRoutingPolicy(policy_params, policy_version="v1")
    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )
    with pytest.raises(PolicyError, match="candidates must not be empty"):
        policy.select(ctx, [])


def test_select_no_scoreable_candidates_raises_policy_error() -> None:
    # Arms in policy do not cover candidates
    policy_params = _make_policy({"arm-x": _make_arm(DIM)})
    policy = BanditRoutingPolicy(policy_params, policy_version="v1")
    cand = _make_candidate("arm-y")
    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )
    with pytest.raises(PolicyError, match="no scoreable candidate model found"):
        policy.select(ctx, [cand])


def test_exploration_rate_must_be_finite() -> None:
    policy_params = _make_policy({"m1": _make_arm(DIM)})
    config = ExplorationConfig(rate_for=lambda _: float("nan"), max_cost_micro=1000)
    policy = BanditRoutingPolicy(policy_params, policy_version="v1", exploration=config)
    cand = _make_candidate("m1")
    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )
    with pytest.raises(PolicyError, match="exploration rate must be finite"):
        policy.select(ctx, [cand])


def test_action_probability_math_and_empty_explore_set() -> None:
    # m1 has higher theta -> will be greedy g
    arm_m1 = LinUCBArmV1(theta=[10.0] * DIM, a_inv=_identity_matrix(DIM))
    arm_m2 = LinUCBArmV1(theta=[1.0] * DIM, a_inv=_identity_matrix(DIM))
    policy_params = _make_policy({"m1": arm_m1, "m2": arm_m2})

    cand1 = _make_candidate("m1", fixed_cost=500)
    cand2 = _make_candidate("m2", fixed_cost=200)
    # unscoreable candidate without an arm
    cand3 = _make_candidate("m3", fixed_cost=100)

    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hi",
        tier="ananta",
        context_budget_tokens=100,
    )

    # 1. No exploration config -> epsilon = 0
    policy_no_exp = BanditRoutingPolicy(policy_params, policy_version="v1")
    dec_no_exp = policy_no_exp.select(ctx, [cand1, cand2, cand3])
    assert dec_no_exp.selected_model == "m1"
    assert not dec_no_exp.exploration
    assert dec_no_exp.selection_probability == 1.0
    probs_dict = dict(dec_no_exp.action_probabilities)
    assert probs_dict["m1"] == 1.0
    assert probs_dict["m2"] == 0.0
    assert probs_dict["m3"] == 0.0

    # 2. Exploration with max_cost_micro=300 -> E only contains m2 (cost 200 <= 300; m1 cost 500 > 300)
    # epsilon = 0.4
    config = ExplorationConfig(rate_for=lambda _: 0.4, max_cost_micro=300)
    # Force exploration by using rng that returns 0.1 (< 0.4)
    mock_rng_explore = _FixedRng(0.1)
    policy_exp = BanditRoutingPolicy(
        policy_params, policy_version="v1", exploration=config, rng=mock_rng_explore
    )
    dec_exp = policy_exp.select(ctx, [cand1, cand2, cand3])

    assert dec_exp.exploration is True
    # E = [cand2], so cand2 must be selected when exploring!
    assert dec_exp.selected_model == "m2"
    # p(m1) = (1 - 0.4)*[m1==g] + 0.4*[m1 in E]/|E| = 0.6 + 0 = 0.6
    # p(m2) = (1 - 0.4)*[m2==g] + 0.4*[m2 in E]/|E| = 0 + 0.4/1 = 0.4
    # p(m3) = 0.0 (no arm)
    probs_exp = dict(dec_exp.action_probabilities)
    assert math.isclose(probs_exp["m1"], 0.6, abs_tol=1e-9)
    assert math.isclose(probs_exp["m2"], 0.4, abs_tol=1e-9)
    assert probs_exp["m3"] == 0.0
    assert math.isclose(dec_exp.selection_probability, 0.4, abs_tol=1e-9)

    # 3. Explore set empty because max_cost_micro too small (50 < all costs) -> epsilon = 0
    config_empty_e = ExplorationConfig(rate_for=lambda _: 0.5, max_cost_micro=50)
    policy_empty_e = BanditRoutingPolicy(
        policy_params, policy_version="v1", exploration=config_empty_e
    )
    dec_empty_e = policy_empty_e.select(ctx, [cand1, cand2, cand3])
    assert not dec_empty_e.exploration
    assert dec_empty_e.selected_model == "m1"
    assert dec_empty_e.selection_probability == 1.0


def test_property_bandit_policy_random_adversarial_suite() -> None:
    """Property-style test: >= 500 cases with stdlib random and fixed seeds.

    random contexts × random eligible subsets × adversarial LinUCB params
    (huge, negative, zero weights, arms for unknown models, missing arms).

    Invariants checked:
    1. The returned model is always in the candidate set.
    2. Probabilities sum to 1 (±1e-9).
    3. selection_probability equals dict(action_probabilities)[selected].
    4. ε exploration never selects outside E.
    """
    rng = random.Random(20260927)  # noqa: S311

    all_model_names = [f"model_{i}" for i in range(1, 8)]

    cases_run = 0
    num_iterations = 600

    for iteration in range(num_iterations):
        # 1. Random context
        tier = rng.choice(TIERS)
        input_tokens = rng.randint(1, 4000)
        budget = rng.randint(50, 8000)
        depth = rng.randint(0, 25)
        retry = rng.randint(0, 5)
        slo = rng.choice([None, 500, 1500, 2500, 5000])

        # Generate text with token length roughly input_tokens
        text = "word " * input_tokens

        ctx = build_routing_context(
            request_id=f"req-prop-{iteration}",
            run_id=f"run-prop-{iteration}",
            text=text,
            tier=tier,
            context_budget_tokens=budget,
            conversation_depth=depth,
            retry_number=retry,
            previous_tool_failure=rng.choice([True, False]),
            previous_structured_output_failure=rng.choice([True, False]),
            latency_slo_ms=slo,
        )

        # 2. Random subset of candidates (1 to 6 candidates)
        cand_count = rng.randint(1, 6)
        chosen_model_names = rng.sample(all_model_names, cand_count)
        candidates = [
            _make_candidate(
                m,
                fixed_cost=rng.randint(10, 2000),
                cost_per_token=rng.choice([0.0, 0.001, 0.05]),
            )
            for m in chosen_model_names
        ]

        # 3. Adversarial LinUCB params:
        # Arms include some candidates, maybe some unknown models, maybe missing some candidates.
        # We ensure at least one candidate has an arm so it is scoreable.
        arms: dict[str, LinUCBArmV1] = {}
        # At least one candidate gets an arm
        guaranteed_model = rng.choice(chosen_model_names)
        models_to_arm = {guaranteed_model}
        for m in all_model_names + ["unknown_extra_1", "unknown_extra_2"]:
            if rng.random() > 0.4:
                models_to_arm.add(m)

        for m in models_to_arm:
            # adversarial weights: huge, negative, zero
            weight_type = rng.choice(["huge", "negative", "zero", "mixed"])
            if weight_type == "huge":
                theta = [rng.choice([1e4, 1e5, 5e4]) for _ in range(DIM)]
            elif weight_type == "negative":
                theta = [-1.0 * rng.uniform(0.1, 50.0) for _ in range(DIM)]
            elif weight_type == "zero":
                theta = [0.0] * DIM
            else:
                theta = [rng.uniform(-10.0, 10.0) for _ in range(DIM)]

            arms[m] = LinUCBArmV1(theta=theta, a_inv=_identity_matrix(DIM))

        policy_params = _make_policy(arms, alpha=rng.choice([0.0, 0.2, 0.5, 2.0]))

        # 4. Exploration config
        exploration_enabled = rng.choice([True, False])
        exploration: ExplorationConfig | None = None
        max_cost = rng.randint(100, 3000)
        exp_rate = rng.uniform(0.0, 1.0)
        if exploration_enabled:
            def _rate_fn(_ctx: object, r: float = exp_rate) -> float:
                return r

            exploration = ExplorationConfig(
                rate_for=_rate_fn,
                max_cost_micro=max_cost,
            )

        # Injected deterministic RNG for policy
        policy_rng = random.Random(rng.randint(0, 1_000_000))  # noqa: S311
        policy = BanditRoutingPolicy(
            policy_params,
            policy_version="prop-test-v1",
            exploration=exploration,
            rng=policy_rng,
        )

        decision = policy.select(ctx, candidates)
        cases_run += 1

        # Invariant 1: The returned model is always in the candidate set
        cand_models = [c.model for c in candidates]
        assert decision.selected_model in cand_models

        # Invariant 2: Probabilities sum to 1 (±1e-9)
        total_prob = math.fsum(prob for _, prob in decision.action_probabilities)
        assert math.isclose(total_prob, 1.0, abs_tol=1e-9)

        # Invariant 3: selection_probability equals dict(action_probabilities)[selected]
        action_dict = dict(decision.action_probabilities)
        assert math.isclose(decision.selection_probability, action_dict[decision.selected_model], abs_tol=1e-9)

        # Invariant 4: ε exploration never selects outside E
        total_tokens = ctx.estimated_input_tokens + ctx.context_budget_tokens
        expected_e = [
            c.model
            for c in candidates
            if c.model in arms and c.expected_cost_micro(total_tokens) <= max_cost
        ]
        if decision.exploration:
            assert expected_e, "Exploration was True but E was empty!"
            assert decision.selected_model in expected_e

        # Additional invariant checks
        assert decision.algorithm == "linucb"
        uuid.UUID(decision.decision_id)
        assert decision.eligible_models == tuple(c.model for c in candidates)

    assert cases_run >= 500, f"Expected at least 500 cases, ran {cases_run}"
