"""Redis-backed cross-worker run state: event mirror, owner lease and stop flag.

Every public function is fail-safe. Without ``redis_url``, or on any Redis error, it returns a
safe default (``None``/``False``/nothing) and never raises, so streaming degrades to the
in-process registry. After an error the module pauses Redis calls for a short cooldown so a dead
Redis cannot add a socket timeout to every streamed delta.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import weakref
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from redis.asyncio import Redis

from daily_agent.config import Settings, get_settings

if TYPE_CHECKING:
    from daily_agent.streaming.registry import StreamEvent

logger = logging.getLogger(__name__)

_EVENTS_MAXLEN = 5000
_EVENTS_TTL_SECONDS = 3600
_OWNER_TTL_SECONDS = 60
_STOP_TTL_SECONDS = 120
_TAIL_BLOCK_MS = 1000
_ERROR_COOLDOWN_SECONDS = 5.0
_TERMINAL_EVENTS = frozenset({"run.finished", "run.error"})

# Clients are bound to the event loop that created them; blocking reads get their own client
# because their socket timeout must exceed the XREAD block time.
_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[str, bool], Redis]] = (
    weakref.WeakKeyDictionary()
)
_cooldown_until = 0.0


def _events_key(run_id: str) -> str:
    return f"karmi:run:{run_id}:events"


def _done_key(run_id: str) -> str:
    return f"karmi:run:{run_id}:done"


def _owner_key(run_id: str) -> str:
    return f"karmi:run:{run_id}:owner"


def _stop_key(run_id: str) -> str:
    return f"karmi:run:{run_id}:stop"


def redis_enabled(settings: Settings | None = None) -> bool:
    current = settings if settings is not None else get_settings()
    return bool(current.redis_url)


def _client(*, blocking: bool = False) -> Redis | None:
    """Return a Redis client for the running loop, or None when disabled or cooling down."""
    if time.monotonic() < _cooldown_until:
        return None
    settings = get_settings()
    url = settings.redis_url
    if not url:
        return None
    loop = asyncio.get_running_loop()
    per_loop = _clients.setdefault(loop, {})
    key = (url, blocking)
    client = per_loop.get(key)
    if client is None:
        try:
            timeout = settings.redis_socket_timeout_seconds
            socket_timeout = _TAIL_BLOCK_MS / 1000 + 5.0 if blocking else timeout
            client = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=timeout,
                socket_timeout=socket_timeout,
            )
        except (ValueError, TypeError) as exc:
            _record_failure("client", exc)
            return None
        per_loop[key] = client
    return client


def _record_failure(operation: str, exc: Exception) -> None:
    global _cooldown_until
    _cooldown_until = time.monotonic() + _ERROR_COOLDOWN_SECONDS
    logger.warning(
        "redis_state.%s failed; Redis calls paused for %.0fs: %s",
        operation,
        _ERROR_COOLDOWN_SECONDS,
        exc,
    )


async def mirror_event(run_id: str, event: str, data: dict[str, Any], seq: int | None) -> None:
    """Append one event to the run's Redis stream; terminal events also set the done marker."""
    client = _client()
    if client is None:
        return
    events_key = _events_key(run_id)
    fields: dict[Any, Any] = {
        "event": event,
        "data": json.dumps(data, default=str),
        "seq": "" if seq is None else str(seq),
    }
    try:
        async with client.pipeline(transaction=False) as pipe:
            pipe.xadd(events_key, fields, maxlen=_EVENTS_MAXLEN, approximate=True)
            pipe.expire(events_key, _EVENTS_TTL_SECONDS)
            if event in _TERMINAL_EVENTS:
                pipe.set(_done_key(run_id), "1", ex=_EVENTS_TTL_SECONDS)
            await pipe.execute()
    except Exception as exc:
        _record_failure("mirror_event", exc)


async def tail_events(
    run_id: str, after_seq: int, *, idle_timeout: float = 45.0
) -> AsyncIterator[StreamEvent]:
    """Yield the run's events from the Redis stream, from the start, past ``after_seq``.

    Ends after a terminal event, after ``idle_timeout`` seconds without new events, or on error.
    """
    # Imported lazily: registry imports this module at load time.
    from daily_agent.streaming.registry import StreamEvent

    client = _client(blocking=True)
    if client is None:
        return
    events_key = _events_key(run_id)
    last_id = "0-0"
    idle_since = time.monotonic()
    try:
        while True:
            remaining = idle_timeout - (time.monotonic() - idle_since)
            if remaining <= 0:
                return
            block_ms = max(1, min(_TAIL_BLOCK_MS, int(remaining * 1000)))
            response = await client.xread({events_key: last_id}, count=100, block=block_ms)
            if not response:
                continue
            idle_since = time.monotonic()
            for _, entries in response:
                for entry_id, fields in entries:
                    last_id = entry_id
                    raw_seq = fields.get("seq", "")
                    seq = int(raw_seq) if raw_seq else None
                    if seq is not None and seq <= after_seq:
                        continue
                    event = StreamEvent(
                        event=fields["event"],
                        data=json.loads(fields["data"]),
                        seq=seq,
                    )
                    yield event
                    if event.event in _TERMINAL_EVENTS:
                        return
    except Exception as exc:
        _record_failure("tail_events", exc)


async def run_is_live(run_id: str) -> bool:
    client = _client()
    if client is None:
        return False
    try:
        return bool(await client.exists(_owner_key(run_id)))
    except Exception as exc:
        _record_failure("run_is_live", exc)
        return False


async def mark_owner(run_id: str) -> None:
    """Claim (or refresh) the run's owner lease; the owning worker calls this periodically."""
    client = _client()
    if client is None:
        return
    try:
        await client.set(_owner_key(run_id), "1", ex=_OWNER_TTL_SECONDS)
    except Exception as exc:
        _record_failure("mark_owner", exc)


async def clear_owner(run_id: str) -> None:
    client = _client()
    if client is None:
        return
    try:
        await client.delete(_owner_key(run_id))
    except Exception as exc:
        _record_failure("clear_owner", exc)


async def request_stop(run_id: str) -> bool:
    """Ask the owning worker to stop the run. Returns True when the run currently has an owner."""
    client = _client()
    if client is None:
        return False
    try:
        await client.set(_stop_key(run_id), "1", ex=_STOP_TTL_SECONDS)
        return bool(await client.exists(_owner_key(run_id)))
    except Exception as exc:
        _record_failure("request_stop", exc)
        return False


async def stop_requested(run_id: str) -> bool:
    client = _client()
    if client is None:
        return False
    try:
        return bool(await client.exists(_stop_key(run_id)))
    except Exception as exc:
        _record_failure("stop_requested", exc)
        return False
