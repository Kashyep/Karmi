#!/usr/bin/env python3
"""Sequential benchmark for chat request handling latency.

Starts the local fake provider on port 8765 (never 8000/8001/8900), runs the
backend pointed at it, issues N sequential chat requests (after warmup), and
reports p50 and p95 for client-observed latency and server-side timing logs.

Refuses to run if the configured provider base URL is not localhost.
"""

from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PORTS = {8000, 8001, 8900}
DEFAULT_FAKE_PORT = 8765
DEFAULT_BACKEND_PORT = 8766
DEFAULT_REQUESTS = 200
DEFAULT_WARMUP = 10


class SSEParser:
    """Incremental parser for event/data frames."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
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


def validate_localhost(url: str, label: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname or ""
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(
            f"REFUSING TO RUN: {label} host '{hostname}' is not localhost. "
            "Benchmarking must only target local fake providers."
        )


def validate_port_allowed(port: int, label: str) -> None:
    if port in FORBIDDEN_PORTS:
        raise SystemExit(
            f"REFUSING TO RUN: {label} uses port {port}, which is forbidden "
            f"(forbidden ports: {sorted(FORBIDDEN_PORTS)})."
        )


def wait_for_url(url: str, timeout_s: float = 15.0, check_status: bool = False) -> bool:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if not check_status or resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
            pass
        time.sleep(0.1)
    return False


def calc_stats(samples: list[float]) -> dict[str, Any]:
    if not samples:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "p50": None,
            "p95": None,
            "p99": None,
        }
    sorted_s = sorted(samples)
    n = len(sorted_s)

    def p(pct: float) -> float:
        idx = min(n - 1, max(0, int(round((pct / 100.0) * n)) - 1))
        return sorted_s[idx]

    return {
        "count": n,
        "min": round(sorted_s[0], 2),
        "max": round(sorted_s[-1], 2),
        "mean": round(sum(sorted_s) / n, 2),
        "p50": round(p(50), 2),
        "p95": round(p(95), 2),
        "p99": round(p(99), 2),
    }


def parse_server_timing_logs(
    log_content: str,
) -> tuple[list[float], list[float], list[str]]:
    """Parse server-side timing durations and overheads (in ms) and return durations, overheads, and log lines."""
    durations: list[float] = []
    overheads: list[float] = []
    lines: list[str] = []
    chat_pattern = re.compile(r"chat\.(?:request\.)?(?:timing|end)[^\n]*duration_ms=([0-9.]+)")
    overhead_pattern = re.compile(r"overhead_ms=([0-9.]+)")
    for line in log_content.splitlines():
        m = chat_pattern.search(line)
        if m:
            durations.append(float(m.group(1)))
            lines.append(line.strip())
            om = overhead_pattern.search(line)
            if om:
                overheads.append(float(om.group(1)))
    if not durations:
        fallback_pattern = re.compile(r"chat[^\n]*duration_ms=([0-9.]+)")
        for line in log_content.splitlines():
            m = fallback_pattern.search(line)
            if m:
                durations.append(float(m.group(1)))
                lines.append(line.strip())
    return durations, overheads, lines


def run_single_pass(
    *,
    backend_port: int,
    fake_port: int,
    endpoint: str,
    text: str,
    token_delay: float,
    requests: int,
    warmup: int,
    timing: bool,
    label: str = "",
) -> tuple[list[float], list[float], list[float], list[str]]:
    """Run a single pass of the backend (with timing enabled or disabled).

    Returns (client_latencies, server_durations, server_overheads, sample_lines).
    """
    tmp_dir = Path(os.environ.get("TMPDIR", tempfile.gettempdir())).expanduser().resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    db_path = tmp_dir / f"karmi_bench_{stamp}.db"
    log_path = tmp_dir / f"karmi_bench_backend_{stamp}.log"
    backend_base_url = f"http://127.0.0.1:{backend_port}"

    backend_env = dict(os.environ)
    backend_env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(ROOT / "src"),
                str(ROOT / "scripts"),
                backend_env.get("PYTHONPATH"),
            ],
        )
    )
    backend_env["FAKE_PROVIDER_PORT"] = str(fake_port)
    backend_env["FAKE_PROVIDER_HOST"] = "127.0.0.1"
    backend_env["FAKE_TOKEN_DELAY"] = str(token_delay)
    backend_env["DAILY_AGENT_ENVIRONMENT"] = "development"
    backend_env["DAILY_AGENT_DATABASE_URL"] = f"sqlite+pysqlite:///{db_path.resolve()}"
    backend_env["DAILY_AGENT_DATA_DIR"] = str(tmp_dir)
    backend_env["DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH"] = "true"
    backend_env["DAILY_AGENT_GATEWAY_DAILY_REQUEST_LIMIT"] = "1000000"
    backend_env["DAILY_AGENT_GATEWAY_PAID_RESERVED_REQUESTS"] = "0"
    backend_env["DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO"] = "100000000"
    backend_env["DAILY_AGENT_RATE_LIMIT_PER_MINUTE"] = "10000"
    backend_env["DAILY_AGENT_LIVE_MODELS_ENABLED"] = "true"
    backend_env["DAILY_AGENT_OPENROUTER_ENABLED"] = "true"
    backend_env["DAILY_AGENT_OPENROUTER_API_KEY"] = "fake-local-key"
    backend_env["DAILY_AGENT_CHAT_TIMING_ENABLED"] = "true" if timing else "false"
    backend_env["LOAD_APP_LOG_LEVEL"] = "INFO"

    backend_proc: subprocess.Popen[str] | None = None
    client_latencies: list[float] = []

    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            try:
                backend_proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "load_app:app",
                        "--app-dir",
                        str(ROOT / "scripts"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(backend_port),
                        "--log-level",
                        "info",
                        "--no-access-log",
                    ],
                    cwd=str(ROOT),
                    env=backend_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                if not wait_for_url(
                    f"{backend_base_url}/health", timeout_s=15.0, check_status=True
                ):
                    log_file.flush()
                    err_text = (
                        log_path.read_text(encoding="utf-8", errors="replace")
                        if log_path.exists()
                        else ""
                    )
                    raise RuntimeError(
                        f"Backend failed to start / ready check timed out. Backend log:\n{err_text}"
                    )

                # Issue dev token
                with httpx.Client(base_url=backend_base_url, timeout=10.0) as client:
                    token_res = client.post("/dev/token?role=customer")
                    token_res.raise_for_status()
                    token = token_res.json()["token"]

                    headers = {
                        "Authorization": f"Bearer {token}",
                    }
                    if endpoint == "/v1/chat/stream":
                        headers["Accept"] = "text/event-stream"
                    else:
                        headers["Content-Type"] = "application/json"

                    def issue_one(index: int) -> float:
                        msg_id = f"bench-{stamp}-{index}"
                        payload = {
                            "text": text,
                            "clientMessageId": msg_id,
                        }
                        t0 = time.perf_counter()
                        if endpoint == "/v1/chat/stream":
                            parser = SSEParser()
                            with client.stream(
                                "POST",
                                "/v1/chat/stream",
                                json=payload,
                                headers=headers,
                                timeout=30.0,
                            ) as resp:
                                resp.raise_for_status()
                                for chunk in resp.iter_bytes():
                                    frames = parser.feed(chunk)
                                    terminal = any(
                                        ev in ("run.finished", "run.error") for ev, _ in frames
                                    )
                                    if terminal:
                                        break
                        else:
                            res = client.post(
                                endpoint,
                                json=payload,
                                headers=headers,
                                timeout=30.0,
                            )
                            res.raise_for_status()
                        t1 = time.perf_counter()
                        return (t1 - t0) * 1000.0

                    if warmup > 0:
                        print(f"[{label}] Warming up ({warmup} requests)...")
                        for i in range(warmup):
                            issue_one(i)
                            if i == 0:
                                import sqlite3

                                with sqlite3.connect(str(db_path)) as conn:
                                    conn.execute("UPDATE subscriptions SET plan_id = 'parth'")
                                    conn.execute(
                                        "UPDATE usage_windows SET everyday_limit = 1000000, "
                                        "spend_limit_micro = 1000000000, token_limit = 1000000000"
                                    )
                                    conn.execute(
                                        "UPDATE usage_periods SET spend_limit_micro = 1000000000"
                                    )
                                    conn.execute(
                                        "UPDATE platform_budgets SET spend_limit_micro = 1000000000"
                                    )

                    print(f"[{label}] Running {requests} sequential requests...")
                    for i in range(requests):
                        lat = issue_one(warmup + i)
                        client_latencies.append(lat)
                        if (i + 1) % 50 == 0 or (i + 1) == requests:
                            print(f"  [{label}] [{i + 1}/{requests}] latest: {lat:.1f} ms")

            finally:
                if backend_proc is not None:
                    backend_proc.send_signal(signal.SIGINT)
                    try:
                        backend_proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        backend_proc.kill()
                        backend_proc.wait()
    finally:
        if db_path.exists():
            db_path.unlink(missing_ok=True)

    backend_log_content = ""
    if log_path.exists():
        backend_log_content = log_path.read_text(encoding="utf-8", errors="replace")
        log_path.unlink(missing_ok=True)

    all_durations, all_overheads, sample_lines = parse_server_timing_logs(backend_log_content)
    if len(all_durations) > requests:
        server_durations = all_durations[-requests:]
        display_lines = sample_lines[-requests:]
    else:
        server_durations = all_durations
        display_lines = sample_lines

    server_overheads = all_overheads[-requests:] if len(all_overheads) > requests else all_overheads

    return client_latencies, server_durations, server_overheads, display_lines


def run_benchmark(
    *,
    requests: int,
    warmup: int,
    fake_port: int,
    backend_port: int,
    endpoint: str,
    text: str,
    token_delay: float,
    timing: bool = True,
    compare: bool = False,
    rounds: int = 3,
    json_out: Path | None = None,
) -> int:
    validate_port_allowed(fake_port, "Fake provider")
    validate_port_allowed(backend_port, "Backend")

    fake_base_url = f"http://127.0.0.1:{fake_port}/api/v1"
    backend_base_url = f"http://127.0.0.1:{backend_port}"

    validate_localhost(fake_base_url, "Fake provider base URL")
    validate_localhost(backend_base_url, "Backend base URL")

    # Double check environment if already set
    existing_openrouter = os.environ.get("OPENROUTER_BASE_URL", "")
    if existing_openrouter:
        validate_localhost(existing_openrouter, "OPENROUTER_BASE_URL")

    print("=== Karmi Chat Request Latency Benchmark ===")
    print(f"Endpoint: {endpoint}")
    print(f"Requests per pass: {requests} (warmup: {warmup})")
    print(f"Fake provider port: {fake_port}")
    print(f"Backend port: {backend_port}")
    print(f"Fake token delay: {token_delay}s")
    if compare:
        print(f"Mode: A/B Comparison ({rounds} rounds of [BEFORE, AFTER])")
    else:
        print(f"Mode: Single Pass (timing={'enabled' if timing else 'disabled'})")

    fake_proc: subprocess.Popen[bytes] | None = None

    try:
        # Start fake provider if not already running
        if not wait_for_url(f"{fake_base_url}/models", timeout_s=0.5):
            print(f"Starting local fake provider on port {fake_port}...")
            fake_env = dict(os.environ)
            fake_env["FAKE_TOKEN_DELAY"] = str(token_delay)
            fake_proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [
                    sys.executable,
                    str(ROOT / "scripts" / "dev_fake_provider.py"),
                    "fake",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(fake_port),
                ],
                cwd=str(ROOT),
                env=fake_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not wait_for_url(f"{fake_base_url}/models", timeout_s=5.0) and not wait_for_url(
                f"http://127.0.0.1:{fake_port}/", timeout_s=5.0
            ):
                raise RuntimeError("Fake provider failed to start")
            print("Fake provider is ready.")
        else:
            print(f"Fake provider already running on port {fake_port}.")

        if not compare:
            client_lats, server_durs, server_ovhs, sample_lines = run_single_pass(
                backend_port=backend_port,
                fake_port=fake_port,
                endpoint=endpoint,
                text=text,
                token_delay=token_delay,
                requests=requests,
                warmup=warmup,
                timing=timing,
                label="PASS",
            )
            client_stats = calc_stats(client_lats)
            server_stats = calc_stats(server_durs)
            overhead_stats = calc_stats(server_ovhs)

            print("\n" + "=" * 50)
            print("BENCHMARK RESULTS")
            print("=" * 50)
            print(f"Endpoint: {endpoint}")
            print(f"Completed requests: {len(client_lats)} (target: {requests})")
            print("\nClient-Observed Latency (ms):")
            print(f"  Count: {client_stats['count']}")
            print(f"  p50:   {client_stats['p50']} ms")
            print(f"  p95:   {client_stats['p95']} ms")
            print(f"  p99:   {client_stats['p99']} ms")
            print(f"  Min:   {client_stats['min']} ms")
            print(f"  Max:   {client_stats['max']} ms")
            print(f"  Mean:  {client_stats['mean']} ms")

            print("\nServer-Side Timing Log Durations (ms):")
            if server_stats["count"] > 0:
                print(f"  Count: {server_stats['count']}")
                print(f"  p50:   {server_stats['p50']} ms")
                print(f"  p95:   {server_stats['p95']} ms")
                print(f"  p99:   {server_stats['p99']} ms")
                print(f"  Min:   {server_stats['min']} ms")
                print(f"  Max:   {server_stats['max']} ms")
                print(f"  Mean:  {server_stats['mean']} ms")
            else:
                print("  None detected (timing middleware disabled)")

            if overhead_stats["count"] > 0:
                print("\nServer-Side Per-Request Middleware Overhead (ms):")
                print(f"  Count: {overhead_stats['count']}")
                print(f"  p50:   {overhead_stats['p50']} ms")
                print(f"  p95:   {overhead_stats['p95']} ms")
                print(f"  Mean:  {overhead_stats['mean']} ms")

            if sample_lines:
                print("\nSample Server Timing Log Lines (first 3):")
                for line in sample_lines[:3]:
                    print(f"  {line}")

            print("=" * 50)

            if json_out is not None:
                report = {
                    "endpoint": endpoint,
                    "requests": requests,
                    "warmup": warmup,
                    "client_stats": client_stats,
                    "server_stats": server_stats,
                    "overhead_stats": overhead_stats,
                    "client_latencies": client_lats,
                    "server_durations": server_durs,
                }
                json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                print(f"Wrote JSON report to {json_out}")
            return 0

        # Compare mode: alternating rounds
        print(f"\nRunning {rounds} alternating rounds of (BEFORE, AFTER)...")
        round_results: list[dict[str, Any]] = []
        for r in range(1, rounds + 1):
            print(f"\n>>> ROUND {r}/{rounds}: BEFORE (timing disabled) <<<")
            b_client, b_server, b_overhead, b_samples = run_single_pass(
                backend_port=backend_port,
                fake_port=fake_port,
                endpoint=endpoint,
                text=text,
                token_delay=token_delay,
                requests=requests,
                warmup=warmup,
                timing=False,
                label=f"R{r}-BEFORE",
            )
            print(f"\n>>> ROUND {r}/{rounds}: AFTER (timing enabled) <<<")
            a_client, a_server, a_overhead, a_samples = run_single_pass(
                backend_port=backend_port,
                fake_port=fake_port,
                endpoint=endpoint,
                text=text,
                token_delay=token_delay,
                requests=requests,
                warmup=warmup,
                timing=True,
                label=f"R{r}-AFTER",
            )
            round_results.append(
                {
                    "round": r,
                    "before": {
                        "client": calc_stats(b_client),
                        "server": calc_stats(b_server),
                        "client_latencies": b_client,
                        "server_durations": b_server,
                    },
                    "after": {
                        "client": calc_stats(a_client),
                        "server": calc_stats(a_server),
                        "overhead": calc_stats(a_overhead),
                        "client_latencies": a_client,
                        "server_durations": a_server,
                        "server_overheads": a_overhead,
                        "samples": a_samples[:3],
                    },
                }
            )

        print("\n" + "=" * 65)
        print("A/B COMPARISON ROUND-BY-ROUND RESULTS")
        print("=" * 65)
        for rr in round_results:
            r = rr["round"]
            bc = rr["before"]["client"]
            ac = rr["after"]["client"]
            asv = rr["after"]["server"]
            aov = rr["after"]["overhead"]
            print(f"\nRound {r}:")
            print(
                f"  BEFORE: Client p50={bc['p50']} ms, p95={bc['p95']} ms | Server: N/A (middleware disabled)"
            )
            print(
                f"  AFTER:  Client p50={ac['p50']} ms, p95={ac['p95']} ms | Server p50={asv['p50']} ms, p95={asv['p95']} ms"
            )
            if aov["count"] > 0:
                print(
                    f"  Direct Middleware Overhead: p50={aov['p50']} ms, p95={aov['p95']} ms, mean={aov['mean']} ms"
                )

        # Median calculations
        b_c_p50s = [
            rr["before"]["client"]["p50"]
            for rr in round_results
            if rr["before"]["client"]["p50"] is not None
        ]
        b_c_p95s = [
            rr["before"]["client"]["p95"]
            for rr in round_results
            if rr["before"]["client"]["p95"] is not None
        ]
        a_c_p50s = [
            rr["after"]["client"]["p50"]
            for rr in round_results
            if rr["after"]["client"]["p50"] is not None
        ]
        a_c_p95s = [
            rr["after"]["client"]["p95"]
            for rr in round_results
            if rr["after"]["client"]["p95"] is not None
        ]
        a_s_p50s = [
            rr["after"]["server"]["p50"]
            for rr in round_results
            if rr["after"]["server"]["p50"] is not None
        ]
        a_s_p95s = [
            rr["after"]["server"]["p95"]
            for rr in round_results
            if rr["after"]["server"]["p95"] is not None
        ]
        a_o_p50s = [
            rr["after"]["overhead"]["p50"]
            for rr in round_results
            if rr["after"]["overhead"]["p50"] is not None
        ]
        a_o_p95s = [
            rr["after"]["overhead"]["p95"]
            for rr in round_results
            if rr["after"]["overhead"]["p95"] is not None
        ]
        a_o_means = [
            rr["after"]["overhead"]["mean"]
            for rr in round_results
            if rr["after"]["overhead"]["mean"] is not None
        ]

        med_b_c_p50 = round(statistics.median(b_c_p50s), 2) if b_c_p50s else None
        med_b_c_p95 = round(statistics.median(b_c_p95s), 2) if b_c_p95s else None
        med_a_c_p50 = round(statistics.median(a_c_p50s), 2) if a_c_p50s else None
        med_a_c_p95 = round(statistics.median(a_c_p95s), 2) if a_c_p95s else None
        med_a_s_p50 = round(statistics.median(a_s_p50s), 2) if a_s_p50s else None
        med_a_s_p95 = round(statistics.median(a_s_p95s), 2) if a_s_p95s else None
        med_a_o_p50 = round(statistics.median(a_o_p50s), 3) if a_o_p50s else None
        med_a_o_p95 = round(statistics.median(a_o_p95s), 3) if a_o_p95s else None
        med_a_o_mean = round(statistics.median(a_o_means), 3) if a_o_means else None

        print("\n" + "=" * 65)
        print("MEDIAN OF ROUNDS SUMMARY")
        print("=" * 65)
        print("BEFORE (Timing Middleware Disabled):")
        print(f"  Client Latency p50:  {med_b_c_p50} ms")
        print(f"  Client Latency p95:  {med_b_c_p95} ms")
        print("  Server Timing Logs:  N/A (middleware disabled)")
        print("\nAFTER (Timing Middleware Enabled):")
        print(f"  Client Latency p50:  {med_a_c_p50} ms")
        print(f"  Client Latency p95:  {med_a_c_p95} ms")
        print(f"  Server Duration p50: {med_a_s_p50} ms")
        print(f"  Server Duration p95: {med_a_s_p95} ms")
        if med_a_o_p50 is not None:
            print("\nPer-Request Middleware Overhead (Direct):")
            print(f"  Overhead p50:        {med_a_o_p50} ms")
            print(f"  Overhead p95:        {med_a_o_p95} ms")
            print(f"  Overhead Mean:       {med_a_o_mean} ms")

        if round_results and round_results[-1]["after"]["samples"]:
            print("\nSample Server Timing Log Lines (from last AFTER run):")
            for line in round_results[-1]["after"]["samples"]:
                print(f"  {line}")

        print("=" * 65)

        if json_out is not None:
            report = {
                "endpoint": endpoint,
                "requests_per_pass": requests,
                "warmup": warmup,
                "rounds": rounds,
                "round_results": round_results,
                "median_summary": {
                    "before_client_p50": med_b_c_p50,
                    "before_client_p95": med_b_c_p95,
                    "after_client_p50": med_a_c_p50,
                    "after_client_p95": med_a_c_p95,
                    "after_server_p50": med_a_s_p50,
                    "after_server_p95": med_a_s_p95,
                    "overhead_p50": med_a_o_p50,
                    "overhead_p95": med_a_o_p95,
                    "overhead_mean": med_a_o_mean,
                },
            }
            json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote JSON report to {json_out}")

        return 0

    finally:
        # Tear down fake provider
        if fake_proc is not None:
            fake_proc.send_signal(signal.SIGINT)
            try:
                fake_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                fake_proc.kill()
                fake_proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-n",
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"Number of sequential requests after warmup (default: {DEFAULT_REQUESTS})",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help=f"Number of warmup requests (default: {DEFAULT_WARMUP})",
    )
    parser.add_argument(
        "--fake-port",
        type=int,
        default=DEFAULT_FAKE_PORT,
        help=f"Port for fake provider (default: {DEFAULT_FAKE_PORT})",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=DEFAULT_BACKEND_PORT,
        help=f"Port for backend (default: {DEFAULT_BACKEND_PORT})",
    )
    parser.add_argument(
        "--endpoint",
        choices=["/v1/chat/stream", "/v1/messages"],
        default="/v1/chat/stream",
        help="Chat endpoint to test (default: /v1/chat/stream)",
    )
    parser.add_argument(
        "--text",
        default="ping",
        help="Message text to send (default: 'ping')",
    )
    parser.add_argument(
        "--token-delay",
        type=float,
        default=0.005,
        help="Token delay in seconds for fake provider (default: 0.005)",
    )
    parser.add_argument(
        "--no-timing",
        action="store_true",
        help="Disable chat timing middleware (single-pass mode)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run alternating A/B rounds (BEFORE vs AFTER) and report round stats and medians",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Number of alternating rounds for --compare mode (default: 3)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Path to write JSON benchmark report",
    )

    args = parser.parse_args()

    if args.requests < 1:
        parser.error("--requests must be at least 1")
    if args.rounds < 1:
        parser.error("--rounds must be at least 1")

    return run_benchmark(
        requests=args.requests,
        warmup=args.warmup,
        fake_port=args.fake_port,
        backend_port=args.backend_port,
        endpoint=args.endpoint,
        text=args.text,
        token_delay=args.token_delay,
        timing=not args.no_timing,
        compare=args.compare,
        rounds=args.rounds,
        json_out=args.json_out,
    )


if __name__ == "__main__":
    raise SystemExit(main())
