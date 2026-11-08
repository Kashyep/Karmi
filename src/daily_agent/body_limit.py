"""Enforce body size limits before JSON parsing on sensitive routes."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MAX_BUG_REPORT_BODY_BYTES = 7 * 1024 * 1024  # 7 MB
_ERROR_BODY = json.dumps({"detail": "request body too large"}).encode("utf-8")


class BodyTooLargeError(Exception):
    """Raised when streaming request body exceeds configured limit."""


class BugReportBodyLimitMiddleware:
    """Pure-ASGI guard enforcing body size limits on POST /v1/bug-reports before JSON parse.

    Rejects requests where Content-Length exceeds MAX_BUG_REPORT_BODY_BYTES immediately.
    When Content-Length is absent or dishonest, counts streamed chunks and aborts with
    HTTP 413 once the cumulative byte count exceeds the threshold.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int = MAX_BUG_REPORT_BODY_BYTES,
        path: str = "/v1/bug-reports",
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path = path.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        request_path = scope.get("path", "").rstrip("/")
        if request_path != self.path:
            await self.app(scope, receive, send)
            return

        # 1. Inspect Content-Length header if present
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value.decode("latin1")) > self.max_bytes:
                        await self._send_413(send)
                        return
                except (ValueError, TypeError):
                    pass

        # 2. Guard against absent or lying Content-Length by counting received chunks
        total_bytes = 0
        too_large = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal total_bytes, too_large
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                total_bytes += len(chunk)
                if total_bytes > self.max_bytes:
                    too_large = True
                    raise BodyTooLargeError()
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if too_large:
                if message.get("type") == "http.response.start" and not response_started:
                    response_started = True
                    await self._send_413(send)
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except BodyTooLargeError:
            pass
        except Exception:
            if not too_large:
                raise

        if too_large and not response_started:
            response_started = True
            await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_ERROR_BODY)).encode("ascii")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": _ERROR_BODY,
            }
        )
