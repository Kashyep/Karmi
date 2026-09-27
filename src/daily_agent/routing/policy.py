"""Routing policy interface (ADR-0003).

Invariants every implementation must hold:

* ``select`` only returns a model present in ``candidates`` (the already-filtered eligible set).
* ``selection_probability`` equals the probability of the returned model in
  ``action_probabilities``; probabilities are finite, in ``[0, 1]`` and sum to 1.
* No training, I/O or mutable global state; exploration randomness comes from an injected RNG.
* Raise :class:`~daily_agent.routing.models.PolicyError` instead of guessing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from daily_agent.routing.models import ModelCandidate, RoutingContext, RoutingDecision


class RoutingPolicy(Protocol):
    @property
    def policy_version(self) -> str: ...

    def select(
        self,
        context: RoutingContext,
        candidates: Sequence[ModelCandidate],
    ) -> RoutingDecision: ...
