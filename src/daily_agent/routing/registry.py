"""Model registry and provider health (circuit breaker).

Route ids are the values Karmi already reports in ``MessageView.route``. Entitlements
preserve pre-router behaviour: every tier may use both routes; live use is additionally
gated by ``DAILY_AGENT_LIVE_MODELS_ENABLED`` in eligibility. ``PlanPolicy.allowed_routes``
names synthetic routes that were never executed or enforced, so it is not consulted here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from daily_agent import providers
from daily_agent.providers import (
    TYPESAFE_INPUT_MICRO_PER_1K,
    TYPESAFE_MODEL_DEFAULT,
    TYPESAFE_OUTPUT_MICRO_PER_1K,
    TYPESAFE_PROVIDER,
)
from daily_agent.routing.models import TIERS, ModelCandidate

LOCAL_ROUTE = "fake-economy"
LIVE_ROUTE = "typesafe-system-one"
LOCAL_PROVIDER = "local"

# Fixed cost of the deterministic local route (mirrors services.LOCAL_FAKE_COST_MICRO).
LOCAL_ROUTE_COST_MICRO = 100
# Declared, unverified context window for the live route. Revisit against provider docs
# before relying on it for real traffic (same status as the declared rate card).
LIVE_ROUTE_MAX_CONTEXT_TOKENS = 128_000
# The live route answers a single Choice question; a handful of output tokens.
LIVE_ROUTE_EXPECTED_OUTPUT_TOKENS = 16


class ProviderHealth:
    """Consecutive-failure circuit breaker per provider, shared across request threads.

    Opens after ``failure_threshold`` consecutive failures; after ``cooldown_seconds`` one
    request is let through (half-open). Success closes the circuit.
    """

    def __init__(
        self,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def is_healthy(self, provider: str) -> bool:
        with self._lock:
            opened = self._opened_at.get(provider)
            if opened is None:
                return True
            if self._clock() - opened >= self._cooldown:
                # Half-open: allow one probe; a failure re-opens with a fresh timestamp.
                del self._opened_at[provider]
                self._failures[provider] = self._threshold - 1
                return True
            return False

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._failures.pop(provider, None)
            self._opened_at.pop(provider, None)

    def record_failure(self, provider: str) -> None:
        with self._lock:
            count = self._failures.get(provider, 0) + 1
            self._failures[provider] = count
            if count >= self._threshold:
                self._opened_at[provider] = self._clock()

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            providers = set(self._failures) | set(self._opened_at)
            return {
                provider: {
                    "consecutive_failures": self._failures.get(provider, 0),
                    "open": provider in self._opened_at,
                }
                for provider in sorted(providers)
            }


def model_candidates(health: ProviderHealth | None = None) -> tuple[ModelCandidate, ...]:
    """All registered routes with current provider health, in stable id order."""

    def healthy(provider: str) -> bool:
        return True if health is None else health.is_healthy(provider)

    return (
        ModelCandidate(
            provider=LOCAL_PROVIDER,
            model=LOCAL_ROUTE,
            model_version="heuristics-v1",
            max_context_tokens=1_000_000,
            supports_tools=False,
            supports_structured_output=True,
            estimated_input_cost_per_token=0.0,
            estimated_output_cost_per_token=0.0,
            provider_healthy=True,
            fixed_cost_micro=LOCAL_ROUTE_COST_MICRO,
            requires_live_models=False,
            entitled_tiers=frozenset(TIERS),
        ),
        ModelCandidate(
            provider=TYPESAFE_PROVIDER,
            model=LIVE_ROUTE,
            model_version=TYPESAFE_MODEL_DEFAULT,
            max_context_tokens=LIVE_ROUTE_MAX_CONTEXT_TOKENS,
            supports_tools=True,
            supports_structured_output=True,
            estimated_input_cost_per_token=TYPESAFE_INPUT_MICRO_PER_1K / 1000,
            estimated_output_cost_per_token=TYPESAFE_OUTPUT_MICRO_PER_1K / 1000,
            provider_healthy=healthy(TYPESAFE_PROVIDER),
            expected_output_tokens=LIVE_ROUTE_EXPECTED_OUTPUT_TOKENS,
            requires_live_models=True,
            spend_bounds_verified=providers.LIVE_PROVIDER_SPEND_VERIFIED,
            entitled_tiers=frozenset(TIERS),
        ),
    )


def entitlement_map() -> dict[str, frozenset[str]]:
    """Route id -> entitled tiers; the verifier's source of known model ids."""
    return {candidate.model: candidate.entitled_tiers for candidate in model_candidates()}
