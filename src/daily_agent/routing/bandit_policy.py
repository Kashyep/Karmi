"""Bandit routing policy using LinUCB parameters (ADR-0003).

Selects routes using verified LinUCB parameters with explicit, controlled exploration.
Karmi executes and evaluates; it never updates parameters online.
"""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from daily_agent.policy_artifacts import scoring
from daily_agent.policy_artifacts.schema import LinUCBPolicyV1
from daily_agent.routing import features
from daily_agent.routing.models import (
    FEATURE_NAMES_V1,
    FEATURE_SCHEMA_VERSION,
    ModelCandidate,
    PolicyError,
    RoutingContext,
    RoutingDecision,
)


@dataclass(frozen=True)
class ExplorationConfig:
    """Exploration budget and rate function for bandit routing."""

    rate_for: Callable[[RoutingContext], float]
    max_cost_micro: int


class BanditRoutingPolicy:
    """LinUCB contextual bandit policy with epsilon-greedy exploration mixture."""

    def __init__(
        self,
        params: LinUCBPolicyV1,
        *,
        policy_version: str,
        exploration: ExplorationConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if params.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise PolicyError(
                f"unsupported feature schema version: {params.feature_schema_version!r}, "
                f"expected {FEATURE_SCHEMA_VERSION!r}"
            )
        if params.dimension != len(FEATURE_NAMES_V1):
            raise PolicyError(
                f"policy dimension {params.dimension} does not match "
                f"feature schema dimension {len(FEATURE_NAMES_V1)}"
            )

        self._params = params
        self._policy_version = policy_version
        self._exploration = exploration
        self._rng = rng if rng is not None else random.SystemRandom()

    @property
    def policy_version(self) -> str:
        return self._policy_version

    def select(
        self,
        context: RoutingContext,
        candidates: Sequence[ModelCandidate],
    ) -> RoutingDecision:
        if not candidates:
            raise PolicyError("candidates must not be empty")

        try:
            x = features.feature_vector(context)
            candidate_map = {c.model: c for c in candidates}
            g = scoring.greedy_model(self._params, candidate_map.keys(), x)
            if g is None or g not in candidate_map:
                raise PolicyError("no scoreable candidate model found")

            epsilon = 0.0
            e_set: list[ModelCandidate] = []
            if self._exploration is not None:
                rate = self._exploration.rate_for(context)
                if not math.isfinite(rate):
                    raise PolicyError("exploration rate must be finite")
                epsilon = min(1.0, max(0.0, float(rate)))
                total_tokens = context.estimated_input_tokens + context.context_budget_tokens
                e_set = [
                    c
                    for c in candidates
                    if c.model in self._params.arms
                    and c.expected_cost_micro(total_tokens) <= self._exploration.max_cost_micro
                ]
                if not e_set:
                    epsilon = 0.0

            len_e = len(e_set)
            e_models = {c.model for c in e_set}

            action_probabilities_list: list[tuple[str, float]] = []
            for c in candidates:
                if c.model not in self._params.arms:
                    p = 0.0
                else:
                    greedy_term = (1.0 - epsilon) if c.model == g else 0.0
                    explore_term = (
                        (epsilon / len_e) if (len_e > 0 and c.model in e_models) else 0.0
                    )
                    p = greedy_term + explore_term
                action_probabilities_list.append((c.model, p))

            prob_map = dict(action_probabilities_list)

            u = self._rng.random()
            is_exploring = u < epsilon
            if is_exploring and e_set:
                sorted_e = sorted(e_set, key=lambda c: c.model)
                selected = self._rng.choice(sorted_e)
            else:
                is_exploring = False if not e_set else is_exploring
                selected = candidate_map[g]

            selection_prob = prob_map[selected.model]

            return RoutingDecision(
                decision_id=str(uuid.uuid4()),
                selected_model=selected.model,
                selected_provider=selected.provider,
                policy_version=self.policy_version,
                selection_probability=selection_prob,
                exploration=is_exploring,
                eligible_models=tuple(c.model for c in candidates),
                feature_schema_version=context.feature_schema_version,
                algorithm="linucb",
                action_probabilities=tuple(action_probabilities_list),
            )
        except Exception as exc:
            if isinstance(exc, PolicyError):
                raise
            raise PolicyError(f"bandit policy selection failed: {exc}") from exc
