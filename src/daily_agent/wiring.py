"""Builds the process-wide telemetry sink and routing runtime from Settings."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from daily_agent.config import Settings
from daily_agent.db import get_engine
from daily_agent.routing.registry import ProviderHealth
from daily_agent.routing.runtime import RoutingRuntime
from daily_agent.telemetry.collector import NullCollector, TelemetryCollector, TelemetrySink


def build_telemetry(settings: Settings) -> TelemetrySink:
    if not settings.telemetry_enabled:
        return NullCollector()
    factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return TelemetryCollector(
        session_factory=factory,
        queue_size=settings.telemetry_queue_size,
        batch_size=settings.telemetry_batch_size,
        flush_interval_seconds=settings.telemetry_flush_interval_seconds,
        spool_path=settings.telemetry_spool_path,
        attribution_window_seconds=settings.telemetry_attribution_window_seconds,
    )


def build_routing_runtime(settings: Settings) -> RoutingRuntime:
    return RoutingRuntime(
        health=ProviderHealth(
            failure_threshold=settings.router_circuit_failure_threshold,
            cooldown_seconds=settings.router_circuit_cooldown_seconds,
        )
    )
