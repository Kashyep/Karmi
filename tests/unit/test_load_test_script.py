"""Exercises scripts/load_test_sse.py against a tiny in-process fake SSE server."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from daily_agent.streaming.sse import encode_sse_event
from scripts.load_test_sse import SSEParser, load_tokens, main, percentile

USERS = 20
BAD_SIG = "bad"


def _token(index: int, sig: str = "ok") -> str:
    return f"synthetic-user-{index}|customer|4102444800|0|{sig}"


async def _chat_stream(request: Request) -> JSONResponse | StreamingResponse:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ")
    fields = token.split("|")
    if len(fields) != 5 or not fields[0].startswith("synthetic-user-"):
        return JSONResponse({"detail": "invalid session"}, status_code=401)
    if fields[4] == "forged":
        return JSONResponse({"detail": "invalid session"}, status_code=401)
    if fields[4] == BAD_SIG:
        return JSONResponse({"detail": "upstream unavailable"}, status_code=503)
    body = await request.json()
    assert body["clientMessageId"].startswith("lt-")
    fail = fields[4] == "fail"

    async def frames() -> AsyncIterator[str]:
        yield encode_sse_event("run.started", {"run_id": "r"}, event_id=0)
        yield encode_sse_event("heartbeat", {"at": "now"})
        for seq in range(1, 4):
            await asyncio.sleep(0.02)
            yield encode_sse_event("message.delta", {"text": "x "}, event_id=seq)
        if fail:
            yield encode_sse_event("run.error", {"category": "INTERNAL", "retryable": True})
        else:
            yield encode_sse_event("run.finished", {"finish_reason": "stop"}, event_id=4)

    return StreamingResponse(frames(), media_type="text/event-stream")


app = Starlette(routes=[Route("/v1/chat/stream", _chat_stream, methods=["POST"])])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def base_url() -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="off",
            timeout_graceful_shutdown=1,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("fake SSE server did not start")
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def _write_tokens(path: Path, tokens: list[str]) -> Path:
    path.write_text("\n".join(tokens) + "\n", encoding="utf-8")
    return path


def test_twenty_distinct_users_all_finish(base_url: str, tmp_path: Path, capsys) -> None:
    tokens = _write_tokens(tmp_path / "tokens.txt", [_token(i) for i in range(USERS)])
    report = tmp_path / "report.json"

    code = main(
        [
            "--base-url",
            base_url,
            "--tokens-file",
            str(tokens),
            "--users",
            str(USERS),
            "--messages-per-user",
            "2",
            "--ramp-seconds",
            "0.2",
            "--timeout",
            "20",
            "--json-out",
            str(report),
        ]
    )

    assert code == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    summary = data["summary"]
    assert summary["total"] == USERS * 2
    assert summary["successes"] == USERS * 2
    assert summary["error_rate"] == 0.0
    assert summary["outcomes"] == {"finished": USERS * 2}
    assert summary["statuses"] == {"200": USERS * 2}
    assert summary["first_delta_s"]["count"] == USERS * 2
    assert summary["first_delta_s"]["p50"] is not None
    assert summary["total_s"]["p99"] >= summary["total_s"]["p50"]
    assert summary["peak_concurrent_streams"] >= 2
    assert all(s["ttfb_s"] is not None for s in data["samples"])
    # Tokens must never leak into the report or stdout.
    assert "synthetic-user-" not in report.read_text(encoding="utf-8")
    assert "synthetic-user-" not in capsys.readouterr().out


def test_error_rate_gate(base_url: str, tmp_path: Path, capsys) -> None:
    tokens = [_token(i) for i in range(USERS)]
    tokens[0] = _token(0, sig=BAD_SIG)  # 503 before the stream starts
    tokens[1] = _token(1, sig="fail")  # run.error terminal event
    path = _write_tokens(tmp_path / "tokens.txt", tokens)
    base = ["--base-url", base_url, "--tokens-file", str(path), "--users", str(USERS)]
    base += ["--ramp-seconds", "0", "--timeout", "20"]

    assert main([*base, "--max-error-rate", "0.01"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "http_error" in out and "run_error" in out

    assert main([*base, "--max-error-rate", "0.10"]) == 0


def test_auth_rejection_is_reported_as_http_status(base_url: str, tmp_path: Path) -> None:
    tokens = [_token(i) for i in range(USERS)]
    tokens[2] = _token(2, sig="forged")  # rejected by the fake server with 401
    path = _write_tokens(tmp_path / "tokens.txt", tokens)
    report = tmp_path / "report.json"

    code = main(
        [
            "--base-url",
            base_url,
            "--tokens-file",
            str(path),
            "--users",
            str(USERS),
            "--ramp-seconds",
            "0",
            "--timeout",
            "20",
            "--json-out",
            str(report),
        ]
    )

    assert code == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    rejected = [s for s in data["samples"] if s["status"] == 401]
    assert len(rejected) == 1 and rejected[0]["user"] == 2


def test_duplicate_principal_is_rejected(tmp_path: Path, capsys) -> None:
    tokens = [_token(0), _token(0), _token(1)]
    path = _write_tokens(tmp_path / "tokens.txt", tokens)

    assert main(["--tokens-file", str(path), "--users", "2"]) == 2
    assert "duplicate principal" in capsys.readouterr().err


def test_too_few_principals_is_rejected(tmp_path: Path) -> None:
    path = _write_tokens(tmp_path / "tokens.txt", [_token(0)])
    with pytest.raises(ValueError, match="needs 3"):
        load_tokens(path, 3)


def test_sse_parser_handles_frames_split_across_chunks() -> None:
    parser = SSEParser()
    raw = (
        "event: message.delta\nid: 1\ndata: {\"text\":\"héllo\"}\n\n"
        ": keep-alive comment\n\nevent: run.finished\ndata: {}\n\n"
    ).encode()
    frames: list[tuple[str, str]] = []
    for i in range(0, len(raw), 7):
        frames.extend(parser.feed(raw[i : i + 7]))
    assert frames == [("message.delta", '{"text":"héllo"}'), ("run.finished", "{}")]


def test_percentile_nearest_rank() -> None:
    values = [float(v) for v in range(1, 101)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile(values, 99) == 99.0
    assert percentile([], 50) is None


def test_run_load_is_importable_for_async_callers(base_url: str) -> None:
    from scripts.load_test_sse import run_load

    samples, wall_s, peak = asyncio.run(
        run_load(base_url, [_token(i) for i in range(3)], 1, 0.0, 20.0, "hi")
    )
    assert len(samples) == 3
    assert wall_s > 0
    assert 1 <= peak <= 3
