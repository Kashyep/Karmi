from typing import Any

import httpx
import pytest

from daily_agent import opencode
from daily_agent.gateway.adapters import OpenRouterProvider
from daily_agent.gateway.health import HealthTracker
from daily_agent.gateway.registry import RegistryError, load_registry, parse_registry
from daily_agent.gateway.router import (
    RouteRequest,
    classify_task,
    eligible_models,
    start_class,
)
from daily_agent.gateway.types import ChatRequest, ModelClass, ProviderError, TaskType
from daily_agent.plans import SYNTHETIC_POLICIES


def entry(model_id: str, model_class: str = "economy", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "model_id": model_id,
        "provider": "openrouter",
        "class": model_class,
        "prompt_price_usd": "0",
        "completion_price_usd": "0",
        "context_length": 32_000,
        "private_data_allowed": False,
        "data_terms": "unknown",
        "scores": {},
    }
    row.update(overrides)
    return row


def registry(*rows: dict[str, Any]) -> Any:
    return parse_registry(
        {"schema_version": "model-registry.v1", "snapshot_date": "2026-10-18", "models": list(rows)}
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"prompt_price_usd": "0.000001"}, "non-zero"),
        ({"completion_price_usd": "0.5"}, "non-zero"),
        ({"class": "premium"}, "unknown class"),
        ({"provider": "mystery"}, "unknown provider"),
        ({"private_data_allowed": True, "data_terms": "unknown"}, "no_training"),
        ({"context_length": 0}, "context_length"),
        ({"scores": {"code": 1.5}}, "within 0..1"),
    ],
)
def test_registry_rejects_unsafe_entries(override: dict[str, Any], message: str) -> None:
    with pytest.raises(RegistryError, match=message):
        registry(entry("vendor/m:free", **override))


def test_registry_rejects_duplicates_and_wrong_schema() -> None:
    with pytest.raises(RegistryError, match="duplicate"):
        registry(entry("vendor/m:free"), entry("vendor/m:free"))
    with pytest.raises(RegistryError, match="schema_version"):
        parse_registry({"schema_version": "model-registry.v0", "models": []})


def test_packaged_seed_is_free_and_private_flags_match_the_opencode_allowlist() -> None:
    seed = load_registry()
    assert seed.models
    opencode_models = [m for m in seed.models if m.provider == "opencode"]
    private = {m.model_id for m in opencode_models if m.private_data_allowed}
    assert private == set(opencode.PRIVATE_DATA_MODEL_IDS)
    assert all(m.model_id in opencode.FREE_MODEL_BY_ID for m in opencode_models)
    assert not any(m.private_data_allowed for m in seed.models if m.provider == "openrouter")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Why is my python function raising a KeyError?\n```py\nd['x']\n```", TaskType.CODE),
        ("Solve 3x + 5 = 20", TaskType.MATHS),
        ("What is the derivative of x^2?", TaskType.MATHS),
        ("Explain how photosynthesis works", TaskType.STUDY),
        ("प्रकाश संश्लेषण क्या है और यह कैसे होता है", TaskType.HINDI),
        ("photosynthesis ko simple words mein समझाओ please", TaskType.MIXED),
        ("Summarise this chapter: " + "The cell is the unit of life. " * 80, TaskType.SUMMARY),
        ("Class 10 science notes please", TaskType.STUDY),
    ],
)
def test_classify_task(text: str, expected: TaskType) -> None:
    assert classify_task(text) == expected


def test_each_plan_starts_in_its_own_class_and_hard_tasks_start_one_higher() -> None:
    def start(plan: str, task: TaskType, *, escalate: bool = False) -> ModelClass | None:
        return start_class(
            RouteRequest(
                plan=SYNTHETIC_POLICIES[plan],
                task_type=task,
                prompt_tokens=10,
                max_output_tokens=10,
                escalate=escalate,
            )
        )

    assert start("ananta", TaskType.STUDY) == ModelClass.ECONOMY
    assert start("ananta", TaskType.CODE) == ModelClass.ECONOMY  # ceiling: economy only
    assert start("yanta", TaskType.STUDY) == ModelClass.ECONOMY
    assert start("yanta", TaskType.CODE) == ModelClass.BALANCED
    assert start("trika", TaskType.STUDY) == ModelClass.BALANCED
    assert start("trika", TaskType.MATHS, escalate=True) == ModelClass.ADVANCED
    assert start("parth", TaskType.STUDY, escalate=True) == ModelClass.ADVANCED


def candidates(reg: Any, plan: str, **kwargs: Any) -> list[str]:
    request = RouteRequest(
        plan=SYNTHETIC_POLICIES[plan],
        task_type=kwargs.pop("task_type", TaskType.STUDY),
        prompt_tokens=kwargs.pop("prompt_tokens", 100),
        max_output_tokens=kwargs.pop("max_output_tokens", 100),
        **kwargs,
    )
    return [m.model_id for m in eligible_models(reg, request, is_available=lambda _m: True)]


def test_candidates_are_ordered_cheapest_class_then_best_score_then_id() -> None:
    reg = registry(
        entry("z-eco", "economy", scores={"study": 0.9}),
        entry("a-eco", "economy", scores={"study": 0.4}),
        entry("m-eco", "economy", scores={"study": 0.9}),
        entry("bal", "balanced", scores={"study": 1.0}),
    )
    assert candidates(reg, "yanta") == ["m-eco", "z-eco", "a-eco", "bal"]


def test_candidates_respect_plan_ceiling_context_privacy_and_structure() -> None:
    reg = registry(
        entry("eco", "economy"),
        entry("small", "economy", context_length=500),
        entry("bal-private", "balanced", private_data_allowed=True, data_terms="no_training"),
        entry("adv", "advanced"),
        entry("eco-structured", "economy", supports_structured_output=True),
    )
    assert candidates(reg, "ananta") == ["eco", "eco-structured", "small"]
    assert candidates(reg, "ananta", prompt_tokens=1_000) == ["eco", "eco-structured"]
    assert candidates(reg, "yanta", structured_output=True) == ["eco-structured"]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_circuit_breaker_opens_probes_once_and_recovers() -> None:
    clock = Clock()
    health = HealthTracker(failure_threshold=3, open_seconds=30, clock=clock)
    server_error = ProviderError(ProviderError.SERVER, "boom")
    for _ in range(2):
        health.record_failure("openrouter", "m", server_error)
    assert health.available("openrouter", "m")
    health.record_failure("openrouter", "m", server_error)
    assert not health.available("openrouter", "m")
    assert health.available("opencode", "m"), "breaker is per provider"
    clock.now += 31
    assert health.available("openrouter", "m"), "half-open after the open window"
    health.begin_call("openrouter")
    assert not health.available("openrouter", "other"), "only one probe at a time"
    health.record_success("openrouter")
    assert health.available("openrouter", "other")


def test_failed_probe_reopens_the_breaker() -> None:
    clock = Clock()
    health = HealthTracker(failure_threshold=1, open_seconds=30, clock=clock)
    error = ProviderError(ProviderError.TIMEOUT, "slow")
    health.record_failure("openrouter", "m", error)
    clock.now += 31
    health.begin_call("openrouter")
    health.record_failure("openrouter", "m", error)
    assert not health.available("openrouter", "m")


def test_rate_limit_cools_one_model_not_the_provider_and_expires() -> None:
    clock = Clock()
    health = HealthTracker(default_cooldown_seconds=60, clock=clock)
    health.record_failure(
        "openrouter", "a", ProviderError(ProviderError.RATE_LIMITED, "429", retry_after_seconds=10)
    )
    assert not health.available("openrouter", "a")
    assert health.available("openrouter", "b")
    clock.now += 11
    assert health.available("openrouter", "a")
    health.record_failure("openrouter", "b", ProviderError(ProviderError.RATE_LIMITED, "429"))
    clock.now += 59
    assert not health.available("openrouter", "b"), "default cooldown applies without Retry-After"


def test_non_zero_price_disables_the_model_permanently() -> None:
    health = HealthTracker()
    health.record_failure("openrouter", "a", ProviderError(ProviderError.NON_ZERO_PRICE, "paid"))
    assert not health.available("openrouter", "a")
    health.record_success("openrouter")
    assert not health.available("openrouter", "a")


MODEL = registry(entry("vendor/m:free")).models[0]
REQUEST = ChatRequest("vendor/m:free", ({"role": "user", "content": "hi"},), 64)


def ok_body(**usage: Any) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, **usage},
    }


def provider(handler: Any) -> OpenRouterProvider:
    return OpenRouterProvider(api_key="sk-or-synthetic", transport=httpx.MockTransport(handler))


def test_openrouter_success_reports_free_zero_cost_call() -> None:
    result = provider(lambda _r: httpx.Response(200, json=ok_body())).complete(REQUEST, MODEL)
    assert result.text == "hello"
    assert result.call.provider == "openrouter"
    assert (result.call.input_tokens, result.call.output_tokens, result.call.cost_micro) == (
        3,
        1,
        0,
    )


@pytest.mark.parametrize(
    ("response", "kind"),
    [
        (httpx.Response(429, headers={"retry-after": "7"}), ProviderError.RATE_LIMITED),
        (httpx.Response(401), ProviderError.AUTH),
        (httpx.Response(402), ProviderError.AUTH),
        (httpx.Response(503), ProviderError.SERVER),
        (httpx.Response(400), ProviderError.REJECTED),
        (
            httpx.Response(302, headers={"location": "https://evil.example/"}),
            ProviderError.REJECTED,
        ),
        (httpx.Response(200, content=b"<html>"), ProviderError.INVALID),
        (httpx.Response(200, json={"choices": []}), ProviderError.INVALID),
        (httpx.Response(200, json=ok_body(cost=0.0001)), ProviderError.NON_ZERO_PRICE),
    ],
)
def test_openrouter_maps_failures_to_provider_error_kinds(
    response: httpx.Response, kind: str
) -> None:
    with pytest.raises(ProviderError) as caught:
        provider(lambda _r: response).complete(REQUEST, MODEL)
    assert caught.value.kind == kind
    if response.status_code == 429:
        assert caught.value.retry_after_seconds == 7


def test_openrouter_never_follows_redirects_or_leaks_the_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(307, headers={"location": "https://evil.example/steal"})

    instance = provider(handler)
    with pytest.raises(ProviderError):
        instance.complete(REQUEST, MODEL)
    assert len(seen) == 1
    assert "sk-or-synthetic" not in repr(instance)


def test_openrouter_timeout_is_a_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as caught:
        provider(handler).complete(REQUEST, MODEL)
    assert caught.value.kind == ProviderError.TIMEOUT


def test_openrouter_bounds_request_size_before_any_call() -> None:
    calls: list[httpx.Request] = []
    instance = provider(lambda r: calls.append(r) or httpx.Response(200, json=ok_body()))
    too_long = ChatRequest("vendor/m:free", ({"role": "user", "content": "x" * 130_000},), 64)
    with pytest.raises(ProviderError) as caught:
        instance.complete(too_long, MODEL)
    assert caught.value.kind == ProviderError.REJECTED
    assert calls == []


def test_unmeasured_task_scores_fall_back_to_the_mean_of_measured_ones() -> None:
    model = registry(entry("m", scores={"maths": 1.0, "hindi": 0.5})).models[0]
    assert model.score("maths") == 1.0
    assert model.score("code") == 0.75
    assert registry(entry("n")).models[0].score("code") == 0.0
