"""Server-Sent Events (SSE) encoding and framing for Karmi streaming."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

SSE_HEADERS = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _json_default(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def encode_sse_event(
    event: str,
    data: dict[str, Any] | BaseModel | str,
    event_id: int | None = None,
) -> str:
    """Encode an SSE frame:

    event: <event>
    id: <event_id> (optional)
    data: <json>

    Terminated by a blank line (\\n\\n).
    """
    if isinstance(data, BaseModel):
        payload = data.model_dump(by_alias=False, exclude_none=True)
        data_str = json.dumps(payload, separators=(",", ":"), default=_json_default)
    elif isinstance(data, dict):
        payload = {k: v for k, v in data.items() if v is not None}
        data_str = json.dumps(payload, separators=(",", ":"), default=_json_default)
    elif isinstance(data, str):
        data_str = data
    else:
        data_str = json.dumps(data, separators=(",", ":"), default=_json_default)

    lines: list[str] = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {data_str}")
    return "\n".join(lines) + "\n\n"


def sse_heartbeat_frame(now: datetime | None = None) -> str:
    """Generate a heartbeat SSE frame."""
    at = now or datetime.now(UTC)
    return encode_sse_event("heartbeat", {"at": at.isoformat()})
