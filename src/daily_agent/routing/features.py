"""Routing feature extraction and context construction (ADR-0003).

Pure functions transforming user requests into stable, non-sensitive feature vectors.
Raw user text never leaves this module; only derived numerical features and coarse
categorical domain labels are exported.
"""

from __future__ import annotations

import math

from daily_agent.routing.models import (
    FEATURE_NAMES_V1,
    FEATURE_SCHEMA_VERSION,
    TASK_DOMAINS,
    TIERS,
    RoutingContext,
)

LOG1P_32000 = math.log1p(32000)

_REMINDER_KEYWORDS: tuple[str, ...] = ("remind me", "reminder")
_TASK_KEYWORDS: tuple[str, ...] = ("to-do", "todo", "task", "add to my list")
_MEMORY_STORE_KEYWORDS: tuple[str, ...] = ("note that", "save this", "remember that")
_MEMORY_QUERY_KEYWORDS: tuple[str, ...] = ("my notes", "what did i", "do you remember", "recall")
_DRAFT_KEYWORDS: tuple[str, ...] = ("draft", "write", "rewrite", "compose", "email", "reply")


def estimate_tokens(text: str) -> int:
    """Estimate token count from UTF-8 byte length (4 bytes per token, minimum 1).

    Same method as ``services.ContextManifest.counting_method``.
    """
    return max(1, len(text.encode("utf-8")) // 4)


def classify_task_domain(text: str) -> str:
    """Deterministic, casefolded keyword classification into models.TASK_DOMAINS.

    Precedence:
    reminder > task > memory_store > memory_query > draft > general.
    Only the categorical label leaves this function.
    """
    lowered = text.casefold().strip()

    if any(kw in lowered for kw in _REMINDER_KEYWORDS):
        return "reminder"
    if any(kw in lowered for kw in _TASK_KEYWORDS):
        return "task"
    if any(kw in lowered for kw in _MEMORY_STORE_KEYWORDS):
        return "memory_store"
    if any(kw in lowered for kw in _MEMORY_QUERY_KEYWORDS) or lowered.startswith("remember"):
        return "memory_query"
    if any(kw in lowered for kw in _DRAFT_KEYWORDS):
        return "draft"
    return "general"


def build_routing_context(
    *,
    request_id: str,
    run_id: str,
    text: str,
    tier: str,
    context_budget_tokens: int,
    conversation_depth: int = 0,
    retry_number: int = 0,
    previous_tool_failure: bool = False,
    previous_structured_output_failure: bool = False,
    latency_slo_ms: int | None = None,
) -> RoutingContext:
    """Build a stable RoutingContext from request inputs without retaining user text."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier: {tier!r}; valid tiers are {TIERS}")

    task_domain = classify_task_domain(text)
    assert task_domain in TASK_DOMAINS

    estimated_input_tokens = estimate_tokens(text)
    if context_budget_tokens <= 0:
        context_utilization_ratio = 0.0
    else:
        context_utilization_ratio = min(1.0, estimated_input_tokens / context_budget_tokens)

    # The v1 API has no request-level tool/structured-output declaration, so
    # requires_tools=False, requires_structured_output=False, tool_count=0,
    # requires_external_data=False; requires_memory = task_domain == "memory_query".
    # The domain one-hot carries the soft signal.
    requires_memory = task_domain == "memory_query"

    return RoutingContext(
        request_id=request_id,
        run_id=run_id,
        tier=tier,
        task_domain=task_domain,
        estimated_input_tokens=estimated_input_tokens,
        context_budget_tokens=context_budget_tokens,
        context_utilization_ratio=context_utilization_ratio,
        tool_count=0,
        requires_structured_output=False,
        requires_tools=False,
        requires_memory=requires_memory,
        requires_external_data=False,
        conversation_depth=conversation_depth,
        retry_number=retry_number,
        previous_tool_failure=previous_tool_failure,
        previous_structured_output_failure=previous_structured_output_failure,
        latency_slo_ms=latency_slo_ms,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
    )


def feature_vector(context: RoutingContext) -> tuple[float, ...]:
    """Ordered numeric feature vector matching FEATURE_NAMES_V1 exactly.

    All values are finite floats in [0, 1].
    """
    if context.feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported feature schema version: {context.feature_schema_version!r}, "
            f"expected {FEATURE_SCHEMA_VERSION!r}"
        )
    if context.tier not in TIERS:
        raise ValueError(f"unknown tier: {context.tier!r}")

    bias = 1.0
    domain_memory_query = 1.0 if context.task_domain == "memory_query" else 0.0
    domain_memory_store = 1.0 if context.task_domain == "memory_store" else 0.0
    domain_task = 1.0 if context.task_domain == "task" else 0.0
    domain_reminder = 1.0 if context.task_domain == "reminder" else 0.0
    domain_draft = 1.0 if context.task_domain == "draft" else 0.0
    domain_general = 1.0 if context.task_domain == "general" else 0.0

    tokens = max(0, context.estimated_input_tokens)
    input_tokens_log = min(1.0, max(0.0, math.log1p(tokens) / LOG1P_32000))
    context_utilization = min(1.0, max(0.0, float(context.context_utilization_ratio)))
    tool_count_norm = min(max(context.tool_count, 0), 4) / 4.0

    requires_structured_output = 1.0 if context.requires_structured_output else 0.0
    requires_tools = 1.0 if context.requires_tools else 0.0
    requires_memory = 1.0 if context.requires_memory else 0.0
    requires_external_data = 1.0 if context.requires_external_data else 0.0

    conversation_depth_norm = min(max(context.conversation_depth, 0), 20) / 20.0
    tier_level_norm = TIERS.index(context.tier) / 3.0
    retry_number_norm = min(max(context.retry_number, 0), 3) / 3.0

    previous_tool_failure = 1.0 if context.previous_tool_failure else 0.0
    previous_structured_output_failure = (
        1.0 if context.previous_structured_output_failure else 0.0
    )
    latency_slo_tight = (
        1.0 if context.latency_slo_ms is not None and context.latency_slo_ms <= 2000 else 0.0
    )

    vec = (
        bias,
        domain_memory_query,
        domain_memory_store,
        domain_task,
        domain_reminder,
        domain_draft,
        domain_general,
        input_tokens_log,
        context_utilization,
        tool_count_norm,
        requires_structured_output,
        requires_tools,
        requires_memory,
        requires_external_data,
        conversation_depth_norm,
        tier_level_norm,
        retry_number_norm,
        previous_tool_failure,
        previous_structured_output_failure,
        latency_slo_tight,
    )
    return vec


def named_features(context: RoutingContext) -> dict[str, float]:
    """Map of FEATURE_NAMES_V1 to numeric feature values."""
    return dict(zip(FEATURE_NAMES_V1, feature_vector(context), strict=True))
