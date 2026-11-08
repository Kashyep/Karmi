"""Scale-path tests: bounded sync-stream hand-off and upstream close on early consumer exit."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncGenerator, Iterator
from typing import cast

from daily_agent.gateway.service import _stream_with_timeouts
from daily_agent.gateway.types import StreamChunk


class _Upstream:
    """Endless sync generator that records production count and close."""

    def __init__(self) -> None:
        self.closed = threading.Event()
        self.produced = 0

    def stream(self) -> Iterator[StreamChunk]:
        try:
            while True:
                self.produced += 1
                yield StreamChunk(text="x")
        finally:
            self.closed.set()


def _chunks(stream: Iterator[StreamChunk]) -> AsyncGenerator[StreamChunk, None]:
    return cast(
        AsyncGenerator[StreamChunk, None],
        _stream_with_timeouts(stream, first_timeout=5.0, gap_timeout=5.0),
    )


def test_early_consumer_exit_stops_worker_and_closes_upstream() -> None:
    upstream = _Upstream()

    async def scenario() -> None:
        chunks = _chunks(upstream.stream())
        first = await chunks.__anext__()
        assert first.text == "x"
        await chunks.aclose()

    asyncio.run(scenario())
    assert upstream.closed.wait(timeout=5.0), "upstream sync stream was not closed"


def test_handoff_is_bounded_while_consumer_is_idle() -> None:
    upstream = _Upstream()

    async def scenario() -> None:
        chunks = _chunks(upstream.stream())
        await chunks.__anext__()
        # Give the worker time to run ahead; it must stop at the hand-off bound.
        await asyncio.sleep(0.3)
        ahead = upstream.produced
        await asyncio.sleep(0.3)
        assert upstream.produced == ahead, "worker kept producing without a consumer"
        assert ahead <= 1 + 8 + 1
        await chunks.aclose()

    asyncio.run(scenario())
    assert upstream.closed.wait(timeout=5.0)


def test_sync_stream_completion_delivers_all_chunks() -> None:
    def gen() -> Iterator[StreamChunk]:
        for text in ("a", "b", "c"):
            yield StreamChunk(text=text)

    async def scenario() -> list[str]:
        return [chunk.text async for chunk in _chunks(gen())]

    assert asyncio.run(scenario()) == ["a", "b", "c"]


def test_sync_stream_error_is_raised_to_consumer() -> None:
    def gen() -> Iterator[StreamChunk]:
        yield StreamChunk(text="a")
        raise ValueError("boom")

    async def scenario() -> None:
        async for _ in _chunks(gen()):
            pass

    try:
        asyncio.run(scenario())
    except ValueError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected ValueError")


def test_worker_thread_exits_after_early_stop() -> None:
    upstream = _Upstream()

    async def scenario() -> None:
        chunks = _chunks(upstream.stream())
        await chunks.__anext__()
        await chunks.aclose()

    asyncio.run(scenario())
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not any(t.name == "gateway-sync-stream" and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.05)
    raise AssertionError("gateway-sync-stream worker thread still alive")
