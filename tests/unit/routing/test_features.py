"""Unit tests for routing feature extraction and context building (ADR-0003)."""

from __future__ import annotations

import math

import pytest

from daily_agent.routing.features import (
    LOG1P_32000,
    build_routing_context,
    classify_task_domain,
    estimate_tokens,
    feature_vector,
    named_features,
)
from daily_agent.routing.models import (
    FEATURE_NAMES_V1,
    FEATURE_SCHEMA_VERSION,
    TIERS,
    RoutingContext,
)


def test_estimate_tokens() -> None:
    # Empty string still yields at least 1 token
    assert estimate_tokens("") == 1
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("a" * 120) == 30
    # Multi-byte UTF-8
    assert estimate_tokens("こんにちは") == max(1, 15 // 4)


@pytest.mark.parametrize(
    ("text", "expected_domain"),
    [
        # Precedence: reminder > task
        ("Remind me to check my to-do list", "reminder"),
        ("Reminder: add to my list", "reminder"),
        # Precedence: task > memory_store
        ("Task: note that the milk is expired", "task"),
        ("To-do: save this for tomorrow", "task"),
        ("Add to my list: remember that we have meeting", "task"),
        # Precedence: memory_store > memory_query
        ("Remember that I like black coffee", "memory_store"),
        ("Save this note about my notes", "memory_store"),
        ("Note that what did I do is recorded", "memory_store"),
        # Precedence: memory_query > draft
        ("What did I write in my notes yesterday?", "memory_query"),
        ("Do you remember when I wrote that email?", "memory_query"),
        ("Recall the draft from earlier", "memory_query"),
        ("My notes on drafting proposals", "memory_query"),
        # memory_query: starts with remember (and not remember that)
        ("Remember my dentist appointment tomorrow", "memory_query"),
        ("  remember to call aunt Sarah", "memory_query"),
        # Precedence: draft > general
        ("Draft a quick reply to the client", "draft"),
        ("Write a short thank-you email", "draft"),
        ("Rewrite this paragraph please", "draft"),
        ("Compose a message", "draft"),
        ("Reply to the thread", "draft"),
        # general fallback
        ("The quick brown fox jumps over the lazy dog", "general"),
        ("What is the capital of France?", "general"),
        ("12345 67890", "general"),
    ],
)
def test_domain_precedence_table(text: str, expected_domain: str) -> None:
    assert classify_task_domain(text) == expected_domain


def test_build_routing_context_success() -> None:
    ctx = build_routing_context(
        request_id="req-123",
        run_id="run-456",
        text="Remind me to call Alice",
        tier="ananta",
        context_budget_tokens=1000,
        conversation_depth=2,
        retry_number=1,
        previous_tool_failure=True,
        previous_structured_output_failure=False,
        latency_slo_ms=1500,
    )
    assert ctx.request_id == "req-123"
    assert ctx.run_id == "run-456"
    assert ctx.tier == "ananta"
    assert ctx.task_domain == "reminder"
    assert ctx.estimated_input_tokens == estimate_tokens("Remind me to call Alice")
    assert ctx.context_budget_tokens == 1000
    assert 0.0 < ctx.context_utilization_ratio < 1.0
    assert ctx.tool_count == 0
    assert not ctx.requires_structured_output
    assert not ctx.requires_tools
    assert not ctx.requires_memory
    assert not ctx.requires_external_data
    assert ctx.conversation_depth == 2
    assert ctx.retry_number == 1
    assert ctx.previous_tool_failure
    assert not ctx.previous_structured_output_failure
    assert ctx.latency_slo_ms == 1500
    assert ctx.feature_schema_version == FEATURE_SCHEMA_VERSION


def test_build_routing_context_requires_memory_for_query() -> None:
    ctx = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="What did I note down?",
        tier="yanta",
        context_budget_tokens=500,
    )
    assert ctx.task_domain == "memory_query"
    assert ctx.requires_memory is True


def test_build_routing_context_unknown_tier_rejected() -> None:
    with pytest.raises(ValueError, match="unknown tier"):
        build_routing_context(
            request_id="r1",
            run_id="r2",
            text="hello",
            tier="nonexistent_tier",
            context_budget_tokens=500,
        )


def test_build_routing_context_budget_bounds() -> None:
    ctx_zero = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hello",
        tier="trika",
        context_budget_tokens=0,
    )
    assert ctx_zero.context_utilization_ratio == 0.0

    ctx_negative = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="hello",
        tier="trika",
        context_budget_tokens=-50,
    )
    assert ctx_negative.context_utilization_ratio == 0.0

    ctx_overflow = build_routing_context(
        request_id="r1",
        run_id="r2",
        text="a" * 400,  # 100 tokens
        tier="trika",
        context_budget_tokens=50,
    )
    assert ctx_overflow.context_utilization_ratio == 1.0


def test_golden_feature_vectors_identical_fixtures() -> None:
    """Golden fixtures producing exact, identical, deterministic feature vectors."""
    ctx_ananta = build_routing_context(
        request_id="req-gold-1",
        run_id="run-gold-1",
        text="Remind me to buy groceries",
        tier="ananta",
        context_budget_tokens=2000,
        conversation_depth=5,
        retry_number=0,
        previous_tool_failure=False,
        previous_structured_output_failure=False,
        latency_slo_ms=1800,
    )
    vec1 = feature_vector(ctx_ananta)
    vec2 = feature_vector(ctx_ananta)
    assert vec1 == vec2

    # Vector length and order match FEATURE_NAMES_V1
    assert len(vec1) == len(FEATURE_NAMES_V1)
    named = named_features(ctx_ananta)
    assert tuple(named.keys()) == FEATURE_NAMES_V1
    assert tuple(named.values()) == vec1

    # Verify individual values of the golden vector
    tokens = estimate_tokens("Remind me to buy groceries")
    expected_log = min(1.0, math.log1p(tokens) / LOG1P_32000)
    expected_util = min(1.0, tokens / 2000)

    assert named["bias"] == 1.0
    assert named["domain_reminder"] == 1.0
    assert named["domain_task"] == 0.0
    assert named["domain_memory_query"] == 0.0
    assert named["domain_memory_store"] == 0.0
    assert named["domain_draft"] == 0.0
    assert named["domain_general"] == 0.0
    assert math.isclose(named["input_tokens_log"], expected_log, rel_tol=1e-9)
    assert math.isclose(named["context_utilization"], expected_util, rel_tol=1e-9)
    assert named["tool_count_norm"] == 0.0
    assert named["requires_structured_output"] == 0.0
    assert named["requires_tools"] == 0.0
    assert named["requires_memory"] == 0.0
    assert named["requires_external_data"] == 0.0
    assert named["conversation_depth_norm"] == 5 / 20.0
    assert named["tier_level_norm"] == 0.0 / 3.0  # ananta is index 0
    assert named["retry_number_norm"] == 0.0 / 3.0
    assert named["previous_tool_failure"] == 0.0
    assert named["previous_structured_output_failure"] == 0.0
    assert named["latency_slo_tight"] == 1.0  # 1800 <= 2000


@pytest.mark.parametrize("tier_idx,tier_name", list(enumerate(TIERS)))
def test_feature_vector_all_tiers_and_ranges(tier_idx: int, tier_name: str) -> None:
    ctx = build_routing_context(
        request_id="req-range",
        run_id="run-range",
        text="Some draft text",
        tier=tier_name,
        context_budget_tokens=1000,
        conversation_depth=30,  # exceeds 20 -> should clamp to 1.0
        retry_number=5,  # exceeds 3 -> should clamp to 1.0
        latency_slo_ms=2500,  # > 2000 -> 0.0
    )
    vec = feature_vector(ctx)
    assert len(vec) == len(FEATURE_NAMES_V1)
    for i, val in enumerate(vec):
        assert math.isfinite(val), f"feature {FEATURE_NAMES_V1[i]} is not finite: {val}"
        assert 0.0 <= val <= 1.0, f"feature {FEATURE_NAMES_V1[i]} out of [0, 1]: {val}"

    named = named_features(ctx)
    assert math.isclose(named["tier_level_norm"], tier_idx / 3.0, rel_tol=1e-9)
    assert named["conversation_depth_norm"] == 1.0
    assert named["retry_number_norm"] == 1.0
    assert named["latency_slo_tight"] == 0.0


def test_feature_vector_schema_version_mismatch() -> None:
    ctx = RoutingContext(
        request_id="r1",
        run_id="r2",
        tier="ananta",
        task_domain="general",
        estimated_input_tokens=10,
        context_budget_tokens=100,
        context_utilization_ratio=0.1,
        tool_count=0,
        requires_structured_output=False,
        requires_tools=False,
        requires_memory=False,
        requires_external_data=False,
        conversation_depth=0,
        retry_number=0,
        previous_tool_failure=False,
        previous_structured_output_failure=False,
        latency_slo_ms=None,
        feature_schema_version="routing-features-v999",
    )
    with pytest.raises(ValueError, match="unsupported feature schema version"):
        feature_vector(ctx)


def test_feature_vector_unknown_tier_in_context() -> None:
    ctx = RoutingContext(
        request_id="r1",
        run_id="r2",
        tier="invalid_tier",
        task_domain="general",
        estimated_input_tokens=10,
        context_budget_tokens=100,
        context_utilization_ratio=0.1,
        tool_count=0,
        requires_structured_output=False,
        requires_tools=False,
        requires_memory=False,
        requires_external_data=False,
        conversation_depth=0,
        retry_number=0,
        previous_tool_failure=False,
        previous_structured_output_failure=False,
        latency_slo_ms=None,
    )
    with pytest.raises(ValueError, match="unknown tier"):
        feature_vector(ctx)
