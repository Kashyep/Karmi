"""Scale infrastructure: config bounds, shared rate limiting, and SSE-safe compression."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Iterator

import pytest
import redis
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from daily_agent.config import Settings
from daily_agent.gzip_middleware import SSEAwareGZip
from daily_agent.ratelimit import RedisSlidingWindowLimiter, SlidingWindowLimiter, build_limiter

REDIS_PORT = 56381
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/0"


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


# --- config ---------------------------------------------------------------------------------


def test_scale_settings_defaults() -> None:
    settings = _settings()
    assert settings.database_pool_size == 10
    assert settings.database_max_overflow == 10
    assert settings.database_pool_timeout == 15
    assert settings.database_pool_recycle_seconds == 1800
    assert settings.redis_socket_timeout_seconds == 0.25
    assert settings.retention_purge_enabled is True
    assert settings.retention_purge_interval_seconds == 3600
    assert settings.retention_batch_size == 1000
    assert settings.retention_runs_days == 90
    assert settings.retention_ledger_days == 400
    assert settings.retention_routing_days == 90
    assert settings.retention_outbox_days == 30
    assert settings.retention_inbox_days == 30
    assert settings.reservation_sweep_interval_seconds == 30
    assert settings.run_stale_seconds == 120
    assert settings.gzip_enabled is True
    assert settings.gzip_min_size == 1024
    assert settings.stream_flush_interval_seconds == 2.0
    assert settings.stream_flush_chars == 4096


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_pool_size": 0},
        {"database_pool_size": 101},
        {"database_max_overflow": 101},
        {"redis_socket_timeout_seconds": 0},
        {"stream_flush_chars": 0},
    ],
)
def test_scale_settings_reject_out_of_bounds(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _settings(**overrides)


# --- limiter: in-process fallback when Redis is not configured -----------------------------


def test_build_limiter_without_redis_is_process_local() -> None:
    limiter = build_limiter(_settings(redis_url=None), name="api", limit=2)
    assert isinstance(limiter, SlidingWindowLimiter)
    assert limiter.check("user-a") is None
    assert limiter.check("user-a") is None
    retry_after = limiter.check("user-a")
    assert retry_after is not None and retry_after >= 1
    assert limiter.check("user-b") is None


# --- limiter: Redis errors fall back instead of failing requests ---------------------------


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_redis_limiter_falls_back_when_redis_unreachable() -> None:
    client = redis.Redis.from_url(
        f"redis://127.0.0.1:{_closed_port()}/0",
        socket_timeout=0.25,
        socket_connect_timeout=0.25,
    )
    fallback = SlidingWindowLimiter(limit=1)
    limiter = RedisSlidingWindowLimiter(
        client, name="fallback-test", limit=1, window_seconds=60.0, fallback=fallback
    )
    assert limiter.check("user") is None  # served by the in-process fallback
    assert limiter.check("user") is not None  # fallback still enforces its own limit


# --- limiter: shared Redis backend across instances -----------------------------------------


def _redis_server_available() -> bool:
    if shutil.which("redis-server") is None:
        return False
    try:
        return bool(redis.Redis.from_url(REDIS_URL, socket_timeout=0.25).ping())
    except redis.RedisError:
        return False


@pytest.fixture(scope="module")
def redis_server() -> Iterator[None]:
    if _redis_server_available():
        yield
        return
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("redis-server binary not available")
    proc = subprocess.Popen(  # noqa: S603 - fixed redis-server binary from PATH
        [binary, "--port", str(REDIS_PORT), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _redis_server_available():
                break
            time.sleep(0.05)
        else:
            pytest.skip("redis-server did not start")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_redis_limiter_shared_between_instances(redis_server: None) -> None:
    client = redis.Redis.from_url(REDIS_URL, socket_timeout=0.25)
    name = f"shared-{time.time_ns()}"
    key = "user-shared"
    fallback = SlidingWindowLimiter(limit=3)
    first = RedisSlidingWindowLimiter(
        client, name=name, limit=3, window_seconds=60.0, fallback=fallback
    )
    second = RedisSlidingWindowLimiter(
        client, name=name, limit=3, window_seconds=60.0, fallback=fallback
    )
    try:
        assert first.check(key) is None
        assert second.check(key) is None
        assert first.check(key) is None
        # Limit is shared: the fourth call is rejected by whichever instance receives it.
        assert second.check(key) is not None
        assert first.check(key) is not None
    finally:
        client.delete(f"karmi:rl:{name}:{key}")


# --- gzip: SSE is never compressed, JSON is --------------------------------------------------


def _gzip_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SSEAwareGZip, minimum_size=1024)
    payload = {"text": "x" * 4000}

    @app.get("/json")
    def as_json() -> dict[str, str]:
        return payload

    @app.get("/events")
    async def events() -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            for index in range(3):
                yield f"data: {json.dumps({'i': index, 'pad': 'y' * 2000})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def test_gzip_compresses_large_json() -> None:
    client = TestClient(_gzip_app())
    response = client.get("/json", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.json() == {"text": "x" * 4000}


def test_gzip_never_compresses_event_stream() -> None:
    client = TestClient(_gzip_app())
    response = client.get("/events", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [line for line in response.text.split("\n") if line.startswith("data: ")]
    assert len(frames) == 3
