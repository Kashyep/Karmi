"""Model gateway: registry, adapters, health tracking and the rules router."""

from __future__ import annotations

import httpx

from daily_agent.config import Settings
from daily_agent.gateway.adapters import ChatProvider, OpenCodeProvider, OpenRouterProvider
from daily_agent.gateway.health import HealthTracker
from daily_agent.gateway.registry import ModelRegistry, load_registry
from daily_agent.gateway.service import Gateway


def build_gateway(
    settings: Settings,
    *,
    registry: ModelRegistry | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Gateway:
    """Assemble the gateway from settings. Unconfigured providers are simply not routable."""
    providers: dict[str, ChatProvider] = {}
    if settings.openrouter_enabled and settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            timeout_seconds=settings.gateway_timeout_seconds,
            transport=transport,
        )
    if settings.opencode_enabled and settings.opencode_api_key:
        providers["opencode"] = OpenCodeProvider(
            api_key=settings.opencode_api_key, transport=transport
        )
    return Gateway(
        registry=registry if registry is not None else load_registry(settings.model_registry_path),
        providers=providers,
        health=HealthTracker(
            failure_threshold=settings.gateway_breaker_failure_threshold,
            open_seconds=settings.gateway_breaker_open_seconds,
            default_cooldown_seconds=settings.gateway_model_cooldown_seconds,
        ),
        kill_switch=settings.gateway_kill_switch,
    )


__all__ = ["Gateway", "build_gateway"]
