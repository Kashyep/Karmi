"""Automatic demotion guardrails for a learned *live* policy (bandit or canary).

The monitor only ever demotes (rollback to the previous/last-known-good/static policy). It
never promotes: promotion stays a human decision through the policy CLI.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardrailThresholds:
    window: int
    min_samples: int
    max_failure_rate: float
    max_fallback_rate: float
    max_mean_cost_micro: int | None
    max_p95_latency_ms: int | None


@dataclass(frozen=True)
class _Sample:
    failed: bool
    fell_back: bool
    cost_micro: int | None
    latency_ms: int


class GuardrailMonitor:
    def __init__(self, thresholds: GuardrailThresholds) -> None:
        self._thresholds = thresholds
        self._lock = threading.Lock()
        self._samples: dict[str, deque[_Sample]] = {}

    @property
    def thresholds(self) -> GuardrailThresholds:
        return self._thresholds

    def reset(self, policy_version: str) -> None:
        with self._lock:
            self._samples.pop(policy_version, None)

    def record(
        self,
        policy_version: str,
        *,
        failed: bool,
        fell_back: bool,
        cost_micro: int | None,
        latency_ms: int,
    ) -> str | None:
        """Add one live outcome; return a breach reason code when a threshold is exceeded."""
        with self._lock:
            window = self._samples.setdefault(
                policy_version, deque(maxlen=self._thresholds.window)
            )
            window.append(_Sample(failed, fell_back, cost_micro, latency_ms))
            samples = list(window)
        return self._breach(samples)

    def _breach(self, samples: list[_Sample]) -> str | None:
        limits = self._thresholds
        count = len(samples)
        if count < limits.min_samples:
            return None
        if sum(s.failed for s in samples) / count > limits.max_failure_rate:
            return "guardrail_failure_rate"
        if sum(s.fell_back for s in samples) / count > limits.max_fallback_rate:
            return "guardrail_fallback_rate"
        costs = [s.cost_micro for s in samples if s.cost_micro is not None]
        if (
            limits.max_mean_cost_micro is not None
            and costs
            and sum(costs) / len(costs) > limits.max_mean_cost_micro
        ):
            return "guardrail_cost"
        if limits.max_p95_latency_ms is not None:
            ordered = sorted(s.latency_ms for s in samples)
            p95 = ordered[min(count - 1, int(0.95 * count))]
            if p95 > limits.max_p95_latency_ms:
                return "guardrail_latency"
        return None

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            copied = {version: list(window) for version, window in self._samples.items()}
        return {
            version: {
                "samples": len(samples),
                "failure_rate": sum(s.failed for s in samples) / len(samples),
                "fallback_rate": sum(s.fell_back for s in samples) / len(samples),
            }
            for version, samples in copied.items()
            if samples
        }
