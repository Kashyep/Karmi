"""Cheap in-process request metrics for the admin monitor (polled every ~5 s).

A pure-ASGI middleware appends one ``(time, latency, status)`` tuple per HTTP request to a
bounded deque: O(1) on the request path, no DB or network. With several API replicas each
process reports its own view (same caveat as ``ratelimit`` and ``gateway.health``).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

WINDOW_SECONDS = 60.0
MAX_SAMPLES = 20_000
_IGNORED_PREFIXES = ("/health", "/ready", "/v1/admin/monitor")


class RequestMetrics:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._samples: deque[tuple[float, float, int]] = deque(maxlen=MAX_SAMPLES)

    def record(self, latency_ms: float, status_code: int) -> None:
        with self._lock:
            self._samples.append((self._clock(), latency_ms, status_code))

    def snapshot(self) -> dict[str, float]:
        cutoff = self._clock() - WINDOW_SECONDS
        with self._lock:
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()
            rows = list(self._samples)
        if not rows:
            return {"req_per_min": 0.0, "error_rate": 0.0, "p95_latency_ms": 0.0}
        latencies = sorted(row[1] for row in rows)
        errors = sum(1 for row in rows if row[2] >= 500)
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        return {
            "req_per_min": float(len(rows)),
            "error_rate": errors / len(rows),
            "p95_latency_ms": round(p95, 1),
        }


METRICS = RequestMetrics()


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: RequestMetrics = METRICS) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or path.startswith(_IGNORED_PREFIXES):
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        recorded = False

        async def send_wrapper(message: Message) -> None:
            nonlocal recorded
            if message["type"] == "http.response.start" and not recorded:
                recorded = True
                status_code = int(message["status"])
                # Latency to first byte: SSE streams must not count their whole lifetime.
                self.metrics.record((time.perf_counter() - started) * 1000, status_code)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if not recorded:
                self.metrics.record((time.perf_counter() - started) * 1000, 500)
            raise
