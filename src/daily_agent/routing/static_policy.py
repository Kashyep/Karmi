"""Static routing policy reproducing baseline route selection (ADR-0003)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from daily_agent.routing.models import (
    ModelCandidate,
    PolicyError,
    RoutingContext,
    RoutingDecision,
)
from daily_agent.routing.registry import LIVE_ROUTE, LOCAL_ROUTE

STATIC_POLICY_VERSION = "static-v1"


class StaticRoutingPolicy:
    """Deterministic routing policy with fixed preference order."""

    def __init__(
        self,
        preference: Sequence[str] = (LIVE_ROUTE, LOCAL_ROUTE),
    ) -> None:
        self._preference = tuple(preference)

    @property
    def policy_version(self) -> str:
        return STATIC_POLICY_VERSION

    def select(
        self,
        context: RoutingContext,
        candidates: Sequence[ModelCandidate],
    ) -> RoutingDecision:
        if not candidates:
            raise PolicyError("candidates must not be empty")

        selected: ModelCandidate | None = None
        for pref in self._preference:
            match = next((c for c in candidates if c.model == pref), None)
            if match is not None:
                selected = match
                break

        if selected is None:
            selected = min(candidates, key=lambda c: c.model)

        action_probabilities = tuple(
            (c.model, 1.0 if c.model == selected.model else 0.0)
            for c in candidates
        )

        return RoutingDecision(
            decision_id=str(uuid.uuid4()),
            selected_model=selected.model,
            selected_provider=selected.provider,
            policy_version=self.policy_version,
            selection_probability=1.0,
            exploration=False,
            eligible_models=tuple(c.model for c in candidates),
            feature_schema_version=context.feature_schema_version,
            algorithm="static",
            action_probabilities=action_probabilities,
        )
