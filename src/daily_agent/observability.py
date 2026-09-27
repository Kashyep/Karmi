"""In-process operational metrics for routing, telemetry and policy loading.

No metrics backend is deployed yet, so counters/gauges/latency samples live in memory and
are served redacted through the admin API. Names are stable identifiers; labels are small
enumerations (policy version, model id, reason code), never user data.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Mapping

LabelKey = tuple[tuple[str, str], ...]


def _key(labels: Mapping[str, str] | None) -> LabelKey:
    return tuple(sorted((labels or {}).items()))


class Metrics:
    def __init__(self, sample_window: int = 1_000) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, dict[LabelKey, int]] = {}
        self._gauges: dict[str, dict[LabelKey, float]] = {}
        self._samples: dict[str, deque[float]] = {}
        self._sample_window = sample_window

    def inc(self, name: str, labels: Mapping[str, str] | None = None, amount: int = 1) -> None:
        with self._lock:
            series = self._counters.setdefault(name, {})
            key = _key(labels)
            series[key] = series.get(key, 0) + amount

    def set_gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        with self._lock:
            self._gauges.setdefault(name, {})[_key(labels)] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._samples.setdefault(name, deque(maxlen=self._sample_window)).append(value)

    def counter(self, name: str, labels: Mapping[str, str] | None = None) -> int:
        with self._lock:
            return self._counters.get(name, {}).get(_key(labels), 0)

    def gauge(self, name: str, labels: Mapping[str, str] | None = None) -> float | None:
        with self._lock:
            return self._gauges.get(name, {}).get(_key(labels))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            counters = {
                name: [{"labels": dict(key), "value": value} for key, value in series.items()]
                for name, series in self._counters.items()
            }
            gauges = {
                name: [{"labels": dict(key), "value": value} for key, value in series.items()]
                for name, series in self._gauges.items()
            }
            samples = {name: sorted(values) for name, values in self._samples.items()}
        summaries = {name: _summary(values) for name, values in samples.items()}
        return {"counters": counters, "gauges": gauges, "summaries": summaries}


def _summary(ordered: list[float]) -> dict[str, float | int | None]:
    if not ordered:
        return {"count": 0, "p50": None, "p95": None, "max": None}

    def pct(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]

    return {"count": len(ordered), "p50": pct(0.5), "p95": pct(0.95), "max": ordered[-1]}


# Process-wide registry. Tests may construct their own ``Metrics`` and inject it.
METRICS = Metrics()
