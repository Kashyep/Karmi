"""Shared synchronous Redis client, one per URL.

Returns ``None`` when ``redis_url`` is unset so callers can fall back to in-process state.
Timeouts are short and retries are disabled: Redis is an accelerator, and callers must never
stall a request behind it.
"""

from __future__ import annotations

import threading

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from daily_agent.config import Settings

_lock = threading.Lock()
_clients: dict[str, redis.Redis] = {}


def get_redis(settings: Settings) -> redis.Redis | None:
    url = settings.redis_url
    if not url:
        return None
    with _lock:
        client = _clients.get(url)
        if client is None:
            timeout = settings.redis_socket_timeout_seconds
            client = redis.Redis.from_url(
                url,
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
                retry=Retry(NoBackoff(), 0),
            )
            _clients[url] = client
        return client
