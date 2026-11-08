from datetime import UTC, datetime

from daily_agent.schemas_chat import MessageDeltaPayload
from daily_agent.streaming.sse import SSE_HEADERS, encode_sse_event, sse_heartbeat_frame


def test_sse_headers() -> None:
    assert SSE_HEADERS["Content-Type"] == "text/event-stream; charset=utf-8"
    assert SSE_HEADERS["Cache-Control"] == "no-cache"
    assert SSE_HEADERS["X-Accel-Buffering"] == "no"


def test_encode_sse_event_with_id_and_dict() -> None:
    frame = encode_sse_event(
        event="message.delta",
        data={"text": "hello"},
        event_id=1,
    )
    assert frame == 'event: message.delta\nid: 1\ndata: {"text":"hello"}\n\n'


def test_encode_sse_event_without_id() -> None:
    frame = encode_sse_event(
        event="run.finished",
        data={"finish_reason": "stop", "outcome": "COMPLETED"},
    )
    assert frame == 'event: run.finished\ndata: {"finish_reason":"stop","outcome":"COMPLETED"}\n\n'


def test_encode_sse_event_with_base_model() -> None:
    model = MessageDeltaPayload(text="chunk")
    frame = encode_sse_event(event="message.delta", data=model, event_id=42)
    assert "event: message.delta\n" in frame
    assert "id: 42\n" in frame
    assert 'data: {"text":"chunk"}\n\n' in frame


def test_encode_sse_event_excludes_none() -> None:
    payload = {"finish_reason": "stop", "input_tokens": None, "output_tokens": 10}
    frame = encode_sse_event(event="run.finished", data=payload)
    assert "input_tokens" not in frame
    assert '"output_tokens":10' in frame


def test_sse_heartbeat_frame() -> None:
    now = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
    frame = sse_heartbeat_frame(now)
    assert frame.startswith("event: heartbeat\n")
    assert 'data: {"at":"2026-10-21T12:00:00+00:00"}\n\n' in frame
