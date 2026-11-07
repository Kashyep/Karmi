"""Per-request timing logs for chat request handling.

Logs request arrival (chat.request.start) and completion (chat.request.end) with
start time, end time, duration_ms, HTTP status code, and normalized route.
Never logs prompts, replies, user tokens, message text, or secrets.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
import logging
import os
import re
import time
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

logger = logging.getLogger("daily_agent.chat_timing")

# Normalized chat route definitions: (HTTP method, regex, canonical route)
_CHAT_ROUTES: list[tuple[str, re.Pattern[str], str]] = [
    ("POST", re.compile(r"^/v1/chat/stream/?$"), "/v1/chat/stream"),
    ("POST", re.compile(r"^/v1/messages/?$"), "/v1/messages"),
    ("POST", re.compile(r"^/v1/messages/[^/]+/continue/?$"), "/v1/messages/{assistant_message_id}/continue"),
    ("POST", re.compile(r"^/v1/messages/[^/]+/regenerate/?$"), "/v1/messages/{assistant_message_id}/regenerate"),
    ("POST", re.compile(r"^/v1/runs/[^/]+/stop/?$"), "/v1/runs/{run_id}/stop"),
    ("GET", re.compile(r"^/v1/runs/[^/]+/events/?$"), "/v1/runs/{run_id}/events"),
]


def match_chat_route(method: str, path: str) -> str | None:
    """Return the canonical route template for a chat path, or None if not a chat route."""
    m_upper = method.upper()
    for req_method, pattern, route in _CHAT_ROUTES:
        if req_method == m_upper and pattern.match(path):
            return route
    return None


def is_chat_timing_enabled() -> bool:
    """Return whether chat request timing logs and middleware are enabled.

    Controlled via the DAILY_AGENT_CHAT_TIMING_ENABLED environment variable.
    Defaults to True in all environments.
    """
    val = os.environ.get("DAILY_AGENT_CHAT_TIMING_ENABLED", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


class ChatTimingMiddleware:
    """Pure-ASGI middleware that emits per-request timing logs for chat requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET"))
        route = match_chat_route(method, path)
        if route is None:
            await self.app(scope, receive, send)
            return

        start_dt = datetime.now(UTC)
        start_iso = start_dt.isoformat()
        start_perf = time.perf_counter()

        logger.info(
            "chat.request.start route=%s start=%s",
            route,
            start_iso,
            extra={
                "event": "chat.request.start",
                "route": route,
                "start": start_iso,
            },
        )

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        inner_start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            inner_end = time.perf_counter()
            end_dt = datetime.now(UTC)
            end_iso = end_dt.isoformat()
            duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)
            inner_ms = round((inner_end - inner_start) * 1000.0, 2)
            overhead_ms = round(max(0.0, duration_ms - inner_ms), 3)

            logger.info(
                "chat.request.end route=%s status=%d duration_ms=%.2f overhead_ms=%.3f start=%s end=%s",
                route,
                status_code,
                duration_ms,
                overhead_ms,
                start_iso,
                end_iso,
                extra={
                    "event": "chat.request.end",
                    "route": route,
                    "status": status_code,
                    "duration_ms": duration_ms,
                    "inner_duration_ms": inner_ms,
                    "overhead_ms": overhead_ms,
                    "start": start_iso,
                    "end": end_iso,
                },
            )
