"""Response compression that never touches server-sent event streams.

Compressing or buffering ``text/event-stream`` would hold back chat tokens until the stream ends,
so SSE responses always pass through unmodified and incrementally. Starlette's GZipMiddleware
excludes that media type by default; this wrapper pins it explicitly so a later change to the
exclusion list cannot silently re-enable buffering.
"""

from __future__ import annotations

from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

SSE_MEDIA_TYPE = "text/event-stream"

_EXCLUDED = tuple(dict.fromkeys((*DEFAULT_EXCLUDED_CONTENT_TYPES, SSE_MEDIA_TYPE)))


class SSEAwareGZip:
    """Pure-ASGI gzip middleware; ``text/event-stream`` responses are always passed through."""

    def __init__(self, app: ASGIApp, *, minimum_size: int = 1024) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size, exclude_content_types=_EXCLUDED)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._gzip(scope, receive, send)
