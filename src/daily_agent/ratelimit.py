"""Per-user request rate limiting and log redaction.

The limiter is in-process: with several API replicas each enforces its own window, so the
effective limit is ``replicas * limit``. A shared (Redis) limiter is a deliberate later step.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> int | None:
        """Record a hit; return ``None`` if allowed, else whole seconds until a slot frees."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return max(1, math.ceil(self._window - (now - hits[0])))
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory: drop idle keys
                for idle in [
                    k for k, v in self._hits.items() if not v or now - v[-1] >= self._window
                ]:
                    del self._hits[idle]
            return None


_REDACTIONS = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    (
        re.compile(r"(?i)\b([A-Z_]*(?:API_KEY|SECRET|TOKEN|PASSWORD))=\S+"),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:/\s]+:)[^@\s]+@"), r"\1[REDACTED]@"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


_installed = False


def install_log_redaction() -> None:
    """Redact credentials from every log record at creation time (idempotent)."""
    global _installed  # noqa: PLW0603
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        record.msg = redact(record.getMessage())
        record.args = ()
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
