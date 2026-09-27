"""Shadow routing policy wrapper (ADR-0003).

Runs a shadow policy alongside the live policy for evaluation without affecting
live routing decisions or failing live requests.
"""

from __future__ import annotations

from collections.abc import Sequence

from daily_agent.routing.models import ModelCandidate, RoutingContext, RoutingDecision
from daily_agent.routing.policy import RoutingPolicy


class ShadowRoutingPolicy:
    """Wrapper running live and shadow policies with strict shadow exception isolation."""

    def __init__(self, live: RoutingPolicy, shadow: RoutingPolicy) -> None:
        self._live = live
        self._shadow = shadow

    @property
    def policy_version(self) -> str:
        return self._live.policy_version

    def select(
        self,
        context: RoutingContext,
        candidates: Sequence[ModelCandidate],
    ) -> RoutingDecision:
        return self._live.select(context, candidates)

    def select_both(
        self,
        context: RoutingContext,
        candidates: Sequence[ModelCandidate],
    ) -> tuple[RoutingDecision, RoutingDecision | None, str | None]:
        live_decision = self._live.select(context, candidates)
        shadow_decision: RoutingDecision | None = None
        shadow_error: str | None = None
        try:
            shadow_decision = self._shadow.select(context, candidates)
        except Exception as exc:
            shadow_error = f"shadow_{type(exc).__name__}"
        return live_decision, shadow_decision, shadow_error
