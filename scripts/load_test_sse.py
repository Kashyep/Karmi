"""Concurrent SSE load generator for ``POST /v1/chat/stream``.

Each virtual user uses its own development token (one distinct ``User`` row per user; see
``docs/runbooks/load-test.md``) and sends ``--messages-per-user`` messages sequentially. Each
message reads the SSE stream until ``run.finished`` or ``run.error``.

Measured client-side only: time-to-first-byte (first response body chunk), time-to-first-delta
(first ``message.delta`` event), total duration, outcome, HTTP status, throughput and peak
concurrent open streams. Server-side metrics (pool waits, DB latency) are NOT collected.

Exit status: 0 when the error rate is <= ``--max-error-rate``; 1 otherwise; 2 on bad input.
Tokens are never printed or written to ``--json-out``.
"""

from __future__ import annotations

import argparse
import asyncio
import codecs
import json
import math
import sys
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

DELTA_EVENT = "message.delta"
TERMINAL_EVENTS = frozenset({"run.finished", "run.error"})
SUCCESS_OUTCOME = "finished"
DEFAULT_TEXT = "Load test message: summarize today's plan in one sentence."
CONNECT_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class Sample:
    user: int
    message: int
    outcome: str
    status: int | None
    ttfb_s: float | None
    first_delta_s: float | None
    total_s: float
    detail: str | None = None


class SSEParser:
    """Incremental parser for ``event:``/``data:`` frames separated by blank lines."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""
        self._event = "message"
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[tuple[str, str]]:
        self._buffer += self._decoder.decode(chunk)
        frames: list[tuple[str, str]] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line == "":
                if self._data or self._event != "message":
                    frames.append((self._event, "\n".join(self._data)))
                self._event = "message"
                self._data = []
            elif line.startswith(":"):
                continue
            else:
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value.removeprefix(" ")
                if field == "event":
                    self._event = value
                elif field == "data":
                    self._data.append(value)
        return frames


class _Gauge:
    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        self.current += 1
        self.peak = max(self.peak, self.current)

    def exit(self) -> None:
        self.current -= 1


def _error_detail(data: str) -> str | None:
    try:
        payload: Any = json.loads(data)
    except ValueError:
        return None
    if isinstance(payload, dict):
        category = payload.get("category")
        return str(category) if category is not None else None
    return None


async def _read_stream(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    body: dict[str, str],
    user: int,
    message: int,
) -> Sample:
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
    started = time.perf_counter()
    async with client.stream(
        "POST", f"{base_url}/v1/chat/stream", json=body, headers=headers
    ) as response:
        status = response.status_code
        if status != 200:
            await response.aread()
            return Sample(
                user=user,
                message=message,
                outcome="http_error",
                status=status,
                ttfb_s=None,
                first_delta_s=None,
                total_s=time.perf_counter() - started,
                detail=f"HTTP {status}",
            )
        parser = SSEParser()
        ttfb: float | None = None
        first_delta: float | None = None
        async for chunk in response.aiter_bytes():
            now = time.perf_counter()
            if ttfb is None:
                ttfb = now - started
            for event, data in parser.feed(chunk):
                if event == DELTA_EVENT and first_delta is None:
                    first_delta = now - started
                if event in TERMINAL_EVENTS:
                    finished = event == "run.finished"
                    return Sample(
                        user=user,
                        message=message,
                        outcome=SUCCESS_OUTCOME if finished else "run_error",
                        status=status,
                        ttfb_s=ttfb,
                        first_delta_s=first_delta,
                        total_s=now - started,
                        detail=None if finished else _error_detail(data),
                    )
        return Sample(
            user=user,
            message=message,
            outcome="no_terminal_event",
            status=status,
            ttfb_s=ttfb,
            first_delta_s=first_delta,
            total_s=time.perf_counter() - started,
        )


async def _one_message(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    text: str,
    user: int,
    message: int,
    timeout_s: float,
    gauge: _Gauge,
) -> Sample:
    body = {"text": text, "clientMessageId": f"lt-{uuid.uuid4().hex}"}
    started = time.perf_counter()
    gauge.enter()
    try:
        return await asyncio.wait_for(
            _read_stream(client, base_url, token, body, user, message), timeout=timeout_s
        )
    except TimeoutError:
        return Sample(
            user=user,
            message=message,
            outcome="timeout",
            status=None,
            ttfb_s=None,
            first_delta_s=None,
            total_s=time.perf_counter() - started,
        )
    except httpx.HTTPError as exc:
        return Sample(
            user=user,
            message=message,
            outcome="transport_error",
            status=None,
            ttfb_s=None,
            first_delta_s=None,
            total_s=time.perf_counter() - started,
            detail=type(exc).__name__,
        )
    finally:
        gauge.exit()


async def run_load(
    base_url: str,
    tokens: list[str],
    messages_per_user: int,
    ramp_seconds: float,
    timeout_s: float,
    text: str,
) -> tuple[list[Sample], float, int]:
    users = len(tokens)
    gauge = _Gauge()
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    timeout = httpx.Timeout(timeout_s, connect=CONNECT_TIMEOUT_S)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:

        async def virtual_user(index: int) -> list[Sample]:
            # Linear ramp: user i starts at ramp * i / users seconds.
            await asyncio.sleep(ramp_seconds * index / users)
            results: list[Sample] = []
            for message in range(messages_per_user):
                results.append(
                    await _one_message(
                        client,
                        base_url,
                        tokens[index],
                        text,
                        index,
                        message,
                        timeout_s,
                        gauge,
                    )
                )
            return results

        started = time.perf_counter()
        groups = await asyncio.gather(*(virtual_user(i) for i in range(users)))
        wall_s = time.perf_counter() - started
    return [sample for group in groups for sample in group], wall_s, gauge.peak


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile; ``None`` when there are no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _latency_block(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def summarize(
    samples: list[Sample], wall_s: float, peak_concurrent: int, max_error_rate: float
) -> dict[str, Any]:
    total = len(samples)
    successes = sum(1 for s in samples if s.outcome == SUCCESS_OUTCOME)
    error_rate = (total - successes) / total if total else 1.0
    return {
        "total": total,
        "successes": successes,
        "error_rate": error_rate,
        "max_error_rate": max_error_rate,
        "passed": total > 0 and error_rate <= max_error_rate,
        "outcomes": dict(Counter(s.outcome for s in samples)),
        "statuses": dict(Counter(str(s.status) if s.status is not None else "none" for s in samples)),
        "first_delta_s": _latency_block(
            [s.first_delta_s for s in samples if s.first_delta_s is not None]
        ),
        "total_s": _latency_block([s.total_s for s in samples]),
        "ttfb_s": _latency_block([s.ttfb_s for s in samples if s.ttfb_s is not None]),
        "wall_s": wall_s,
        "requests_per_second": total / wall_s if wall_s > 0 else 0.0,
        "successes_per_second": successes / wall_s if wall_s > 0 else 0.0,
        "peak_concurrent_streams": peak_concurrent,
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def print_summary(summary: dict[str, Any]) -> None:
    print(f"requests: {summary['total']}  successes: {summary['successes']}")
    print(f"error rate: {summary['error_rate']:.4f} (max {summary['max_error_rate']:.4f})")
    print(f"outcomes: {summary['outcomes']}")
    print(f"HTTP statuses: {summary['statuses']}")
    for name in ("first_delta_s", "total_s", "ttfb_s"):
        block = summary[name]
        print(
            f"{name}: n={block['count']} p50={_fmt(block['p50'])} "
            f"p95={_fmt(block['p95'])} p99={_fmt(block['p99'])}"
        )
    print(
        f"wall: {summary['wall_s']:.2f}s  throughput: {summary['requests_per_second']:.2f} req/s, "
        f"{summary['successes_per_second']:.2f} ok/s"
    )
    print(f"peak concurrent streams (client-side): {summary['peak_concurrent_streams']}")
    print("PASS" if summary["passed"] else "FAIL: error rate above threshold or no requests")


def load_tokens(path: Path, users: int) -> list[str]:
    """Return ``users`` tokens, each for a distinct principal (``user_id`` before the first ``|``)."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    candidates = [line for line in lines if line and not line.startswith("#")]
    seen: set[str] = set()
    chosen: list[str] = []
    for token in candidates:
        fields = token.split("|")
        if len(fields) != 5 or not fields[0]:
            raise ValueError("tokens file lines must be development tokens (user_id|role|exp|ver|sig)")
        user_id = fields[0]
        if user_id in seen:
            raise ValueError(f"duplicate principal {user_id}: every user needs a distinct token")
        seen.add(user_id)
        chosen.append(token)
    if len(chosen) < users:
        raise ValueError(f"tokens file has {len(chosen)} principals; --users needs {users}")
    return chosen[:users]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Concurrent SSE load test for /v1/chat/stream.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--tokens-file",
        type=Path,
        required=True,
        help="file with one development token per line, each for a distinct user",
    )
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--messages-per-user", type=int, default=1)
    parser.add_argument("--ramp-seconds", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=120.0, help="per-message total seconds")
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--json-out", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.users < 1 or args.messages_per_user < 1:
        parser.error("--users and --messages-per-user must be >= 1")
    if args.ramp_seconds < 0 or args.timeout <= 0:
        parser.error("--ramp-seconds must be >= 0 and --timeout > 0")
    if not 0 <= args.max_error_rate <= 1:
        parser.error("--max-error-rate must be between 0 and 1")
    try:
        tokens = load_tokens(args.tokens_file, args.users)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    samples, wall_s, peak = asyncio.run(
        run_load(
            args.base_url.rstrip("/"),
            tokens,
            args.messages_per_user,
            args.ramp_seconds,
            args.timeout,
            args.text,
        )
    )
    summary = summarize(samples, wall_s, peak, args.max_error_rate)
    print_summary(summary)
    if args.json_out is not None:
        report = {"summary": summary, "samples": [asdict(s) for s in samples]}
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
