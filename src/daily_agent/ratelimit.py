"""Per-user request rate limiting and log redaction.

Two limiters share the ``check(key) -> int | None`` contract (``None`` = allowed, otherwise the
whole seconds to wait):

* ``SlidingWindowLimiter`` is in-process. Each replica enforces its own window, so the effective
  limit is ``replicas * limit``.
* ``RedisSlidingWindowLimiter`` keeps the window in a Redis sorted set shared by every replica.
  It runs as one Lua script, so the check is atomic. On any Redis error it falls back to an
  in-process limiter and logs the failure at most once a minute.

``build_limiter`` picks the Redis-backed limiter when ``redis_url`` is configured.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import redis

from daily_agent.config import Settings
from daily_agent.redis_client import get_redis

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    def check(self, key: str) -> int | None: ...


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


# KEYS[1]=sorted set, ARGV: now_ms, window_ms, limit, unique member.
# Returns {1, 0} when the hit is recorded, else {0, retry_after_ms}.
_SLIDING_WINDOW_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return {0, tonumber(oldest[2]) + window - now}
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('PEXPIRE', KEYS[1], window)
return {1, 0}
"""

_LOG_INTERVAL_SECONDS = 60.0


class RedisSlidingWindowLimiter:
    """Sliding-window limiter shared across processes through Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        name: str,
        limit: int,
        window_seconds: float,
        fallback: RateLimiter,
    ) -> None:
        self._redis = redis_client
        self._prefix = f"karmi:rl:{name}:"
        self._limit = limit
        self._window_ms = max(1, round(window_seconds * 1000))
        self._fallback = fallback
        self._script = redis_client.register_script(_SLIDING_WINDOW_LUA)
        self._last_error_log = float("-inf")
        self._log_lock = threading.Lock()

    def check(self, key: str) -> int | None:
        now_ms = time.time_ns() // 1_000_000
        try:
            allowed, retry_after_ms = self._script(
                keys=[f"{self._prefix}{key}"],
                args=[now_ms, self._window_ms, self._limit, f"{now_ms}-{uuid.uuid4().hex}"],
            )
        except redis.RedisError as error:
            self._log_failure(error)
            return self._fallback.check(key)
        if int(allowed) == 1:
            return None
        return max(1, math.ceil(int(retry_after_ms) / 1000))

    def _log_failure(self, error: Exception) -> None:
        now = time.monotonic()
        with self._log_lock:
            if now - self._last_error_log < _LOG_INTERVAL_SECONDS:
                return
            self._last_error_log = now
        logger.warning(
            "ratelimit.redis_unavailable prefix=%s falling_back_to_process_limiter error=%s",
            self._prefix,
            type(error).__name__,
        )


def build_limiter(
    settings: Settings,
    *,
    name: str,
    limit: int,
    window_seconds: float = 60.0,
) -> RateLimiter:
    """Shared Redis limiter when ``redis_url`` is set, else a per-process limiter."""
    fallback = SlidingWindowLimiter(limit=limit, window_seconds=window_seconds)
    client = get_redis(settings)
    if client is None:
        return fallback
    return RedisSlidingWindowLimiter(
        client,
        name=name,
        limit=limit,
        window_seconds=window_seconds,
        fallback=fallback,
    )


_REDACTIONS = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "[REDACTED_KEY]"),
    (re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_-]{8,}"), "[REDACTED_KEY]"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    (
        re.compile(r"(?i)\b([A-Z_-]*(?:API_KEY|API-KEY|APIKEY|SECRET|TOKEN|PASSWORD))=\S+"),
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
    """Redact credentials from every log record at creation time (idempotent).

    Records with arguments keep their ``msg`` template untouched (redacting it would eat ``%s``
    placeholders such as ``token=%s``) and only their string arguments are redacted. ``args``
    keeps its shape so %-style formatters that unpack it (e.g. uvicorn's access formatter) work.
    """
    global _installed  # noqa: PLW0603
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        if not record.args and isinstance(record.msg, str):
            record.msg = redact(record.msg)
        elif isinstance(record.args, Mapping):
            record.args = {
                k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()
            }
        elif isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return record

    logging.setLogRecordFactory(factory)

    previous_format = logging.Formatter.format
    previous_format_exception = logging.Formatter.formatException

    def format_exception(self: logging.Formatter, ei: Any) -> str:
        formatted = previous_format_exception(self, ei)
        return redact(formatted)

    def format_record(self: logging.Formatter, record: logging.LogRecord) -> str:
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        result = previous_format(self, record)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return result

    logging.Formatter.format = format_record
    logging.Formatter.formatException = format_exception
    _installed = True
