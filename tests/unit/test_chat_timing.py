import asyncio

import pytest

from daily_agent.chat_timing import (
    ChatTimingMiddleware,
    is_chat_timing_enabled,
    match_chat_route,
)


def test_chat_timing_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DAILY_AGENT_CHAT_TIMING_ENABLED", raising=False)
    assert is_chat_timing_enabled() is False

    monkeypatch.setenv("DAILY_AGENT_CHAT_TIMING_ENABLED", "")
    assert is_chat_timing_enabled() is False

    monkeypatch.setenv("DAILY_AGENT_CHAT_TIMING_ENABLED", "   ")
    assert is_chat_timing_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "True", "yes", "YES", "on", "ON"])
def test_chat_timing_enabled_with_truthy_env(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("DAILY_AGENT_CHAT_TIMING_ENABLED", val)
    assert is_chat_timing_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "FALSE", "no", "off", "random", "disabled"])
def test_chat_timing_disabled_with_falsy_or_unknown_env(
    monkeypatch: pytest.MonkeyPatch, val: str
) -> None:
    monkeypatch.setenv("DAILY_AGENT_CHAT_TIMING_ENABLED", val)
    assert is_chat_timing_enabled() is False


def test_match_chat_route() -> None:
    assert match_chat_route("POST", "/v1/chat/stream") == "/v1/chat/stream"
    assert match_chat_route("POST", "/v1/chat/stream/") == "/v1/chat/stream"
    assert match_chat_route("POST", "/v1/messages") == "/v1/messages"
    assert (
        match_chat_route("POST", "/v1/messages/msg_123/continue")
        == "/v1/messages/{assistant_message_id}/continue"
    )
    assert (
        match_chat_route("POST", "/v1/messages/msg_123/regenerate")
        == "/v1/messages/{assistant_message_id}/regenerate"
    )
    assert match_chat_route("POST", "/v1/runs/run_456/stop") == "/v1/runs/{run_id}/stop"
    assert match_chat_route("GET", "/v1/runs/run_456/events") == "/v1/runs/{run_id}/events"
    # Non-chat routes return None
    assert match_chat_route("GET", "/v1/messages") is None
    assert match_chat_route("GET", "/health") is None


def test_chat_timing_middleware_emits_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DAILY_AGENT_CHAT_TIMING_ENABLED", "1")
    caplog.set_level("INFO", logger="daily_agent.chat_timing")

    async def run_scenario() -> None:
        async def dummy_app(scope, receive, send):  # type: ignore[no-untyped-def]
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = ChatTimingMiddleware(dummy_app)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/stream",
        }

        async def dummy_receive():  # type: ignore[no-untyped-def]
            return {"type": "http.request"}

        messages = []

        async def dummy_send(msg):  # type: ignore[no-untyped-def]
            messages.append(msg)

        await middleware(scope, dummy_receive, dummy_send)

    asyncio.run(run_scenario())
    records = [r for r in caplog.records if r.name == "daily_agent.chat_timing"]
    assert len(records) == 2
    assert records[0].getMessage().startswith("chat.request.start route=/v1/chat/stream")
    assert records[1].getMessage().startswith("chat.request.end route=/v1/chat/stream status=200")
