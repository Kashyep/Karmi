"""Tests for the Redis cross-worker run state helpers (fail-safe contract)."""

from __future__ import annotations

import asyncio
import socket
import uuid
from types import SimpleNamespace

import pytest

from daily_agent.streaming import redis_state

LIVE_URL = "redis://127.0.0.1:56379/15"


def _redis_reachable(url: str) -> bool:
    host_port = url.split("//", 1)[1].split("/", 1)[0]
    host, port = host_port.split(":")
    try:
        with socket.create_connection((host, int(port)), timeout=0.2):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _reset_cooldown() -> None:
    redis_state._cooldown_until = 0.0


def _use_url(monkeypatch: pytest.MonkeyPatch, url: str | None) -> None:
    fake = SimpleNamespace(redis_url=url, redis_socket_timeout_seconds=0.25)
    monkeypatch.setattr(redis_state, "get_settings", lambda: fake)


def test_disabled_without_redis_url_returns_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_url(monkeypatch, None)
    assert redis_state.redis_enabled() is False

    async def scenario() -> list[object]:
        await redis_state.mirror_event("r1", "message.delta", {"text": "x"}, 1)
        await redis_state.mark_owner("r1")
        await redis_state.clear_owner("r1")
        events = [event async for event in redis_state.tail_events("r1", 0, idle_timeout=0.1)]
        return [
            events,
            await redis_state.run_is_live("r1"),
            await redis_state.request_stop("r1"),
            await redis_state.stop_requested("r1"),
        ]

    assert asyncio.run(scenario()) == [[], False, False, False]


def test_unreachable_redis_never_raises_and_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port 1 is never listening; every call must degrade instead of raising.
    _use_url(monkeypatch, "redis://127.0.0.1:1/0")
    assert redis_state.redis_enabled() is True

    async def scenario() -> tuple[bool, bool, bool, list[object]]:
        await redis_state.mirror_event("r2", "run.finished", {}, 3)
        live = await redis_state.run_is_live("r2")
        stop = await redis_state.request_stop("r2")
        events = [event async for event in redis_state.tail_events("r2", 0, idle_timeout=0.1)]
        return live, stop, redis_state._cooldown_until > 0, events

    live, stop, cooling, events = asyncio.run(scenario())
    assert (live, stop, cooling, events) == (False, False, True, [])


def test_bad_url_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_url(monkeypatch, "not-a-valid-url")

    async def scenario() -> bool:
        await redis_state.mirror_event("r3", "message.delta", {"text": "x"}, 1)
        return await redis_state.run_is_live("r3")

    assert asyncio.run(scenario()) is False


@pytest.mark.skipif(not _redis_reachable(LIVE_URL), reason="local redis not reachable")
def test_live_mirror_tail_owner_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_url(monkeypatch, LIVE_URL)
    run_id = uuid.uuid4().hex

    async def scenario() -> tuple[list[tuple[str, int | None]], bool, bool, bool, bool]:
        await redis_state.mark_owner(run_id)
        live = await redis_state.run_is_live(run_id)
        await redis_state.mirror_event(run_id, "message.delta", {"text": "a"}, 1)
        await redis_state.mirror_event(run_id, "message.delta", {"text": "b"}, 2)
        await redis_state.mirror_event(run_id, "run.finished", {"ok": True}, 3)
        events = [
            (event.event, event.seq)
            async for event in redis_state.tail_events(run_id, 1, idle_timeout=5.0)
        ]
        stop = await redis_state.request_stop(run_id)
        requested = await redis_state.stop_requested(run_id)
        await redis_state.clear_owner(run_id)
        after_clear = await redis_state.run_is_live(run_id)
        return events, live, stop, requested, after_clear

    events, live, stop, requested, after_clear = asyncio.run(scenario())
    assert events == [("message.delta", 2), ("run.finished", 3)]
    assert live is True
    assert stop is True
    assert requested is True
    assert after_clear is False
