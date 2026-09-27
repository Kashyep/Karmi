"""Frozen routing contracts (ADR-0003).

These types cross module and repository boundaries: telemetry persists them and Parakh
consumes them through ``TelemetryBatchV1``. Change them only with a schema version bump.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

FEATURE_SCHEMA_VERSION = "routing-features-v1"

# Ordered, normalised numeric features exported to Parakh and consumed by learned policies.
# Index order is part of the contract: a PolicyBundle's feature_schema.json must match exactly.
FEATURE_NAMES_V1: tuple[str, ...] = (
    "bias",
    "domain_memory_query",
    "domain_memory_store",
    "domain_task",
    "domain_reminder",
    "domain_draft",
    "domain_general",
    "input_tokens_log",
    "context_utilization",
    "tool_count_norm",
    "requires_structured_output",
    "requires_tools",
    "requires_memory",
    "requires_external_data",
    "conversation_depth_norm",
    "tier_level_norm",
    "retry_number_norm",
    "previous_tool_failure",
    "previous_structured_output_failure",
    "latency_slo_tight",
)

TASK_DOMAINS: tuple[str, ...] = (
    "memory_query",
    "memory_store",
    "task",
    "reminder",
    "draft",
    "general",
)

TIERS: tuple[str, ...] = ("ananta", "yanta", "trika", "parth")


@dataclass(frozen=True)
class RoutingContext:
    """Stable, non-sensitive request features. Never contains raw user text."""

    request_id: str
    run_id: str
    tier: str
    task_domain: str
    estimated_input_tokens: int
    context_budget_tokens: int
    context_utilization_ratio: float
    tool_count: int
    requires_structured_output: bool
    requires_tools: bool
    requires_memory: bool
    requires_external_data: bool
    conversation_depth: int
    retry_number: int
    previous_tool_failure: bool
    previous_structured_output_failure: bool
    latency_slo_ms: int | None
    feature_schema_version: str = FEATURE_SCHEMA_VERSION


@dataclass(frozen=True)
class ModelCandidate:
    """One executable route. ``model`` is the route id the policy selects."""

    provider: str
    model: str
    model_version: str | None
    max_context_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    # Micro-units per token (the ledger's unit), plus a fixed per-request component.
    estimated_input_cost_per_token: float
    estimated_output_cost_per_token: float
    provider_healthy: bool
    fixed_cost_micro: int = 0
    expected_output_tokens: int = 0
    requires_live_models: bool = False
    spend_bounds_verified: bool = True
    entitled_tiers: frozenset[str] = frozenset(TIERS)

    def expected_cost_micro(self, input_tokens: int) -> int:
        variable = (
            input_tokens * self.estimated_input_cost_per_token
            + self.expected_output_tokens * self.estimated_output_cost_per_token
        )
        return self.fixed_cost_micro + math.ceil(variable)


@dataclass(frozen=True)
class EligibilityResult:
    eligible: tuple[ModelCandidate, ...]
    # model id -> sorted rejection reason codes (see eligibility.REASON_CODES)
    rejections: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def eligible_models(self) -> tuple[str, ...]:
        return tuple(candidate.model for candidate in self.eligible)


@dataclass(frozen=True)
class RoutingDecision:
    decision_id: str
    selected_model: str
    selected_provider: str
    policy_version: str
    # Probability that this policy selects ``selected_model`` given the context and the
    # eligible set. Mandatory for off-policy evaluation; must equal
    # ``dict(action_probabilities)[selected_model]``.
    selection_probability: float
    exploration: bool
    eligible_models: tuple[str, ...]
    feature_schema_version: str
    algorithm: str = "static"
    # Full distribution over ``eligible_models`` (sums to 1.0, ordered like eligible_models).
    action_probabilities: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class RoutingOutcome:
    """Everything the request path learned while routing one request."""

    context: RoutingContext
    feature_vector: tuple[float, ...]
    eligibility: EligibilityResult
    live: RoutingDecision
    shadow: RoutingDecision | None = None
    shadow_error: str | None = None
    # Set when the configured learned policy failed and the static policy served instead.
    live_fallback_reason: str | None = None


class NoEligibleModel(Exception):
    """Every candidate failed a hard constraint; the request must defer, not bypass."""

    def __init__(self, rejections: dict[str, tuple[str, ...]]) -> None:
        super().__init__("no eligible model for this request")
        self.rejections = rejections


class PolicyError(Exception):
    """A policy could not produce a valid decision (callers fall back to static)."""
