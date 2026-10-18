"""In-process provider health: per-provider circuit breaker and per-model cooldowns.

State is per process. With several API workers each keeps its own view; a shared (Redis) view
is a deliberate later step, not hidden here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from daily_agent.gateway.types import ProviderError


@dataclass
class _BreakerState:
    failures: int = 0
    opened_at: float | None = None
    probing: bool = False


class HealthTracker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        open_seconds: float = 60.0,
        default_cooldown_seconds: float = 60.0,
        max_cooldown_seconds: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._default_cooldown = default_cooldown_seconds
        self._max_cooldown = max_cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._breakers: dict[str, _BreakerState] = {}
        self._cooldowns: dict[tuple[str, str], float] = {}
        self._disabled: set[tuple[str, str]] = set()

    def available(self, provider: str, model_id: str) -> bool:
        """Read-only check used for candidate selection (does not claim a half-open probe)."""
        with self._lock:
            if (provider, model_id) in self._disabled:
                return False
            until = self._cooldowns.get((provider, model_id))
            if until is not None and self._clock() < until:
                return False
            state = self._breakers.get(provider)
            if state is None or state.opened_at is None:
                return True
            if self._clock() - state.opened_at < self._open_seconds:
                return False
            return not state.probing

    def begin_call(self, provider: str) -> None:
        """Mark a half-open probe in flight so only one request tests a recovering provider."""
        with self._lock:
            state = self._breakers.get(provider)
            if state is not None and state.opened_at is not None:
                state.probing = True

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._breakers[provider] = _BreakerState()

    def record_failure(self, provider: str, model_id: str, error: ProviderError) -> None:
        with self._lock:
            key = (provider, model_id)
            if error.kind == ProviderError.NON_ZERO_PRICE:
                self._disabled.add(key)
                return
            if error.kind == ProviderError.RATE_LIMITED:
                seconds = error.retry_after_seconds
                if seconds is None or seconds <= 0:
                    seconds = self._default_cooldown
                self._cooldowns[key] = self._clock() + min(seconds, self._max_cooldown)
                self._release_probe(provider)
                return
            if error.kind == ProviderError.REJECTED:
                self._release_probe(provider)
                return
            state = self._breakers.setdefault(provider, _BreakerState())
            state.probing = False
            state.failures += 1
            if error.kind == ProviderError.AUTH or state.failures >= self._threshold:
                state.opened_at = self._clock()

    def _release_probe(self, provider: str) -> None:
        state = self._breakers.get(provider)
        if state is not None:
            state.probing = False

    def provider_open(self, provider: str) -> bool:
        with self._lock:
            state = self._breakers.get(provider)
            return state is not None and state.opened_at is not None
