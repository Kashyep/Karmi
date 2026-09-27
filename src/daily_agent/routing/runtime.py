"""Per-process routing runtime: policy selection, shadowing, canary split, guardrails.

The runtime owns mutable process state (loaded bundles, provider health, guardrail windows).
Configuration comes from the ``Settings`` passed on every call, so request-scoped settings
(and test overrides) always win. Bundles are re-verified from disk whenever the policy store
state revision changes; nothing on disk is trusted between verifications.
"""

from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from daily_agent import __version__
from daily_agent.config import Settings
from daily_agent.harness.versioning import BUILTIN_HARNESS
from daily_agent.observability import METRICS, Metrics
from daily_agent.plans import PlanPolicy
from daily_agent.policy_artifacts.schema import HarnessBundleV1, LoadedBundle
from daily_agent.policy_artifacts.store import PolicyState, PolicyStore
from daily_agent.policy_artifacts.verifier import BundleRejected
from daily_agent.routing.bandit_policy import BanditRoutingPolicy, ExplorationConfig
from daily_agent.routing.eligibility import filter_eligible, require_eligible
from daily_agent.routing.features import feature_vector
from daily_agent.routing.guardrails import GuardrailMonitor, GuardrailThresholds
from daily_agent.routing.models import (
    EligibilityResult,
    RoutingContext,
    RoutingDecision,
    RoutingOutcome,
)
from daily_agent.routing.policy import RoutingPolicy
from daily_agent.routing.registry import ProviderHealth, entitlement_map, model_candidates
from daily_agent.routing.shadow_policy import ShadowRoutingPolicy
from daily_agent.routing.static_policy import StaticRoutingPolicy
from daily_agent.telemetry.events import OpsEventRecord

logger = logging.getLogger(__name__)

OpsSink = Callable[[OpsEventRecord], None]


@dataclass(frozen=True)
class _Live:
    policy: RoutingPolicy
    bundle: LoadedBundle | None
    fallback_reason: str | None


def canary_bucket(actor_id: str) -> int:
    """Stable 0-99 bucket per pseudonymous actor, independent of request order."""
    digest = hashlib.sha256(f"karmi-canary-v1:{actor_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100



class RoutingRuntime:
    def __init__(
        self,
        *,
        health: ProviderHealth,
        metrics: Metrics = METRICS,
        ops_sink: OpsSink | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        self.health = health
        self._metrics = metrics
        self._ops_sink = ops_sink
        self._monotonic = monotonic
        self._rng = rng or random.SystemRandom()
        self._lock = threading.Lock()
        self._static = StaticRoutingPolicy()
        self._store: PolicyStore | None = None
        self._store_key: tuple[Path, str | None] | None = None
        self._state: PolicyState | None = None
        self._state_error: str | None = None
        self._bundles: dict[str, LoadedBundle] = {}
        self._bundle_errors: dict[str, str] = {}
        self._last_check = float("-inf")
        self._tripped: set[str] = set()
        self._guardrails: GuardrailMonitor | None = None

    # ---- configuration / state ---------------------------------------------------------

    def set_ops_sink(self, sink: OpsSink | None) -> None:
        self._ops_sink = sink

    def _emit_ops(self, event_type: str, *, detail: str | None, version: str | None) -> None:
        if self._ops_sink is None:
            return
        try:
            self._ops_sink(
                OpsEventRecord(
                    event_id=str(uuid.uuid4()),
                    event_type=event_type,
                    detail=detail,
                    policy_version=version,
                    created_at=datetime.now(UTC),
                )
            )
        except Exception:  # telemetry must never break routing
            logger.exception("ops event emission failed")

    def store_for(self, settings: Settings) -> PolicyStore:
        key = (settings.router_policy_dir.resolve(), settings.router_policy_public_key)
        with self._lock:
            if self._store is None or self._store_key != key:
                self._store = PolicyStore(
                    settings.router_policy_dir,
                    public_key_b64=settings.router_policy_public_key,
                    known_models=entitlement_map(),
                    karmi_version=__version__,
                    metrics=self._metrics,
                )
                self._store_key = key
                self._state = None
                self._bundles = {}
                self._bundle_errors = {}
                self._last_check = float("-inf")
            return self._store

    def _guardrail_monitor(self, settings: Settings) -> GuardrailMonitor:
        thresholds = GuardrailThresholds(
            window=settings.router_guardrail_window,
            min_samples=settings.router_guardrail_min_samples,
            max_failure_rate=settings.router_guardrail_max_failure_rate,
            max_fallback_rate=settings.router_guardrail_max_fallback_rate,
            max_mean_cost_micro=settings.router_guardrail_max_mean_cost_micro,
            max_p95_latency_ms=settings.router_guardrail_max_p95_latency_ms,
        )
        with self._lock:
            if self._guardrails is None or self._guardrails.thresholds != thresholds:
                self._guardrails = GuardrailMonitor(thresholds)
            return self._guardrails

    def refresh(self, settings: Settings, *, force: bool = False) -> None:
        """Re-read the store state (throttled) and re-verify bundles when it changed."""
        if settings.router_mode == "static":
            return
        store = self.store_for(settings)
        now = self._monotonic()
        with self._lock:
            if not force and now - self._last_check < settings.router_reload_interval_seconds:
                return
            self._last_check = now
        try:
            state = store.read_state()
        except Exception as exc:
            with self._lock:
                self._state, self._state_error = None, type(exc).__name__
                self._bundles = {}
            self._metrics.inc("policy_state_errors_total")
            self._emit_ops("policy_state_unreadable", detail=type(exc).__name__, version=None)
            logger.error("policy store state unreadable; serving static routing: %s", exc)
            return
        with self._lock:
            unchanged = self._state is not None and self._state.revision == state.revision
        if unchanged and not force:
            return
        wanted = {version for version in (state.active, state.shadow) if version is not None}
        bundles: dict[str, LoadedBundle] = {}
        errors: dict[str, str] = {}
        for version in sorted(wanted):
            try:
                bundles[version] = store.load(version)
            except BundleRejected as exc:
                errors[version] = exc.code
            except Exception as exc:
                errors[version] = type(exc).__name__
            if version in errors:
                self._metrics.inc("policy_load_failures_total", {"code": errors[version]})
                self._emit_ops("policy_bundle_rejected", detail=errors[version], version=version)
                logger.error("policy bundle %s rejected at load: %s", version, errors[version])
        with self._lock:
            self._state, self._state_error = state, None
            self._bundles, self._bundle_errors = bundles, errors

    # ---- routing -----------------------------------------------------------------------

    def _bundle_policy(
        self, bundle: LoadedBundle, exploration: ExplorationConfig | None
    ) -> BanditRoutingPolicy:
        return BanditRoutingPolicy(
            bundle.policy,
            policy_version=bundle.manifest.artifact_version,
            exploration=exploration,
            rng=self._rng,
        )

    def _exploration(self, settings: Settings) -> ExplorationConfig | None:
        if not settings.router_exploration_enabled:
            return None
        tiers = frozenset(settings.router_exploration_tiers)
        domains = frozenset(settings.router_exploration_domains)
        rate = settings.router_max_exploration_rate

        def rate_for(context: RoutingContext) -> float:
            allowed = context.tier in tiers and context.task_domain in domains
            return rate if allowed else 0.0

        return ExplorationConfig(
            rate_for=rate_for, max_cost_micro=settings.router_exploration_max_cost_micro
        )

    def _live(self, settings: Settings, actor_id: str) -> _Live:
        mode = settings.router_mode
        if mode in {"static", "shadow"}:
            return _Live(self._static, None, None)
        with self._lock:
            state, state_error = self._state, self._state_error
            bundles, errors = dict(self._bundles), dict(self._bundle_errors)
            tripped = set(self._tripped)
        if state is None:
            return _Live(self._static, None, "policy_state_unavailable" if state_error else None)
        active = state.active
        if active is None:
            return _Live(self._static, None, "no_active_bundle")
        if mode == "canary" and canary_bucket(actor_id) >= settings.router_canary_percent:
            return _Live(self._static, None, None)
        if active in tripped:
            return _Live(self._static, None, "guardrail_tripped")
        bundle = bundles.get(active)
        if bundle is None:
            return _Live(self._static, None, f"bundle_rejected_{errors.get(active, 'missing')}")
        try:
            return _Live(self._bundle_policy(bundle, self._exploration(settings)), bundle, None)
        except Exception as exc:
            return _Live(self._static, None, f"policy_init_{type(exc).__name__}")

    def _shadow(self, settings: Settings) -> tuple[RoutingPolicy | None, str | None]:
        if settings.router_mode == "static":
            return None, None
        with self._lock:
            state = self._state
            bundles, errors = dict(self._bundles), dict(self._bundle_errors)
        if state is None or state.shadow is None:
            return None, None
        bundle = bundles.get(state.shadow)
        if bundle is None:
            return None, f"shadow_bundle_rejected_{errors.get(state.shadow, 'missing')}"
        try:
            return self._bundle_policy(bundle, exploration=None), None
        except Exception as exc:
            return None, f"shadow_init_{type(exc).__name__}"

    def static_after_error(
        self, settings: Settings, context: RoutingContext, plan: PlanPolicy
    ) -> tuple[RoutingDecision, EligibilityResult]:
        """Recover from a router error without bypassing hard eligibility."""
        eligibility = require_eligible(
            filter_eligible(
                context,
                model_candidates(self.health),
                plan=plan,
                disabled_models=settings.router_disabled_models,
                live_models_enabled=settings.live_models_enabled,
            )
        )
        return self._static.select(context, eligibility.eligible), eligibility

    def route(
        self,
        *,
        settings: Settings,
        context: RoutingContext,
        plan: PlanPolicy,
        actor_id: str,
    ) -> RoutingOutcome:
        """Eligibility first, then live (+ shadow) selection. Raises NoEligibleModel."""
        self.refresh(settings)
        live = self._live(settings, actor_id)
        restrictions = (
            {model: list(tiers) for model, tiers in live.bundle.manifest.tier_restrictions.items()}
            if live.bundle is not None
            else None
        )
        eligibility = require_eligible(
            filter_eligible(
                context,
                model_candidates(self.health),
                plan=plan,
                disabled_models=settings.router_disabled_models,
                live_models_enabled=settings.live_models_enabled,
                tier_restrictions=restrictions,
            )
        )
        vector = feature_vector(context)
        shadow_policy, shadow_error = self._shadow(settings)
        fallback_reason = live.fallback_reason
        candidates = eligibility.eligible
        shadow: RoutingDecision | None = None
        try:
            if shadow_policy is not None:
                decision, shadow, error = ShadowRoutingPolicy(live.policy, shadow_policy).select_both(
                    context, candidates
                )
                shadow_error = shadow_error or error
            else:
                decision = live.policy.select(context, candidates)
        except Exception as exc:
            fallback_reason = f"policy_error_{type(exc).__name__}"
            self._metrics.inc("router_policy_errors_total", {"policy": live.policy.policy_version})
            logger.warning("live routing policy failed; serving static: %s", exc)
            if shadow_policy is not None:
                decision, shadow, error = ShadowRoutingPolicy(
                    self._static, shadow_policy
                ).select_both(context, candidates)
                shadow_error = shadow_error or error
            else:
                decision = self._static.select(context, candidates)
        self._count(decision, shadow, fallback_reason, eligibility.rejections)
        return RoutingOutcome(
            context=context,
            feature_vector=vector,
            eligibility=eligibility,
            live=decision,
            shadow=shadow,
            shadow_error=shadow_error,
            live_fallback_reason=fallback_reason,
        )

    def _count(
        self,
        live: RoutingDecision,
        shadow: RoutingDecision | None,
        fallback_reason: str | None,
        rejections: dict[str, tuple[str, ...]],
    ) -> None:
        metrics = self._metrics
        metrics.inc(
            "router_decisions_total",
            {"policy": live.policy_version, "model": live.selected_model},
        )
        if live.exploration:
            metrics.inc("router_exploration_total", {"policy": live.policy_version})
        if fallback_reason is not None:
            metrics.inc("router_policy_fallback_total", {"reason": fallback_reason})
        if shadow is not None:
            agreed = "true" if shadow.selected_model == live.selected_model else "false"
            metrics.inc(
                "router_shadow_decisions_total",
                {"policy": shadow.policy_version, "agreed": agreed},
            )
        for model, reasons in rejections.items():
            for reason in reasons:
                metrics.inc("router_eligibility_rejections_total", {"model": model, "reason": reason})

    def harness_for(self, outcome: RoutingOutcome) -> HarnessBundleV1:
        """Bundle harness only while that bundle is the live policy for this request."""
        if outcome.live.algorithm == "static":
            return BUILTIN_HARNESS
        with self._lock:
            bundle = self._bundles.get(outcome.live.policy_version)
        if bundle is None or bundle.harness is None:
            return BUILTIN_HARNESS
        return bundle.harness

    # ---- feedback from the executed request -------------------------------------------

    def observe_provider(self, provider: str, *, success: bool) -> None:
        if success:
            self.health.record_success(provider)
        else:
            self.health.record_failure(provider)

    def after_run(
        self,
        settings: Settings,
        outcome: RoutingOutcome,
        *,
        failed: bool,
        fell_back: bool,
        cost_micro: int | None,
        latency_ms: int,
    ) -> None:
        """Feed guardrails for learned live policies; demote on breach."""
        if outcome.live.algorithm == "static" or not settings.router_guardrails_enabled:
            return
        version = outcome.live.policy_version
        reason = self._guardrail_monitor(settings).record(
            version, failed=failed, fell_back=fell_back, cost_micro=cost_micro, latency_ms=latency_ms
        )
        if reason is not None:
            self.demote(settings, version, reason)

    def demote(self, settings: Settings, version: str, reason: str) -> None:
        with self._lock:
            if version in self._tripped:
                return
            self._tripped.add(version)
        self._metrics.inc("router_guardrail_trips_total", {"reason": reason})
        self._emit_ops("policy_guardrail_rollback", detail=reason, version=version)
        logger.error("guardrail %s tripped for policy %s; rolling back", reason, version)
        persisted = False
        try:
            store = self.store_for(settings)
            # Compare-and-rollback: another actor may already have moved on.
            if store.read_state().active == version:
                store.rollback(reason, expected_active=version)
                self._metrics.inc("policy_rollbacks_total", {"trigger": "guardrail"})
            persisted = True
        except Exception:
            # The in-process trip still forces static routing for this version.
            logger.exception("guardrail rollback could not update the policy store")
        self.refresh(settings, force=True)
        if persisted:
            # The persisted quarantine now governs every worker; an explicit operator
            # promotion lifts it, so this process keeps no permanent private trip.
            self._guardrail_monitor(settings).reset(version)
            with self._lock:
                self._tripped.discard(version)

    # ---- introspection -----------------------------------------------------------------

    def status(self, settings: Settings) -> dict[str, object]:
        self.refresh(settings)
        with self._lock:
            state = self._state
            loaded = sorted(self._bundles)
            errors = dict(self._bundle_errors)
            tripped = sorted(self._tripped)
            guardrails = self._guardrails.snapshot() if self._guardrails else {}
        return {
            "mode": settings.router_mode,
            "static_policy_version": self._static.policy_version,
            "active": state.active if state else None,
            "shadow": state.shadow if state else None,
            "previous": state.previous if state else None,
            "last_known_good": state.last_known_good if state else None,
            "quarantined": list(state.quarantined) if state else [],
            "state_revision": state.revision if state else None,
            "state_error": self._state_error,
            "loaded_bundles": loaded,
            "bundle_errors": errors,
            "guardrail_tripped": tripped,
            "guardrails": guardrails,
            "canary_percent": settings.router_canary_percent,
            "exploration_enabled": settings.router_exploration_enabled,
            "provider_health": self.health.snapshot(),
        }
