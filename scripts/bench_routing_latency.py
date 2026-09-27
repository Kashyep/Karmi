"""Compare synthetic static request latency against a Git baseline (no live calls).

Usage: python scripts/bench_routing_latency.py --baseline-ref 00b7224 --requests 24
Creates only temporary SQLite databases and archives; does not call providers.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _benchmark(source: Path, count: int) -> dict[str, Any]:
    sys.path.insert(0, str(source / "src"))
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from daily_agent import api, config
    from daily_agent.db import Base, get_session
    from daily_agent.models import Account, Subscription, User
    from daily_agent.security import issue_development_token

    with tempfile.TemporaryDirectory(prefix="karmi-static-latency-") as directory:
        db_path = Path(directory) / "workload.db"
        engine = create_engine(
            f"sqlite+pysqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30.0},
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        settings = config.Settings(
            _env_file=None,
            environment="test",
            database_url=f"sqlite+pysqlite:///{db_path}",
            auth_secret="synthetic-benchmark-auth-key",  # noqa: S106
            webhook_secret="synthetic-benchmark-hook-key",  # noqa: S106
            global_daily_budget_micro=200_000,
            live_models_enabled=False,
            telemetry_spool_path=Path(directory) / "spool.jsonl",
        )

        def scoped_session() -> Any:
            with factory() as session:
                yield session

        app = api.create_app()
        app.dependency_overrides[get_session] = scoped_session
        app.dependency_overrides[config.get_settings] = lambda: settings
        api.get_settings = lambda: settings
        if hasattr(app.state, "telemetry"):
            from daily_agent.telemetry.collector import TelemetryCollector

            app.state.telemetry = TelemetryCollector(
                session_factory=factory,
                queue_size=1000,
                batch_size=20,
                flush_interval_seconds=0.05,
                spool_path=settings.telemetry_spool_path,
                attribution_window_seconds=3600,
            )
        with factory() as session:
            account = Account(name="Synthetic benchmark")
            session.add(account)
            session.flush()
            user = User(account_id=account.id, display_name="Load fixture", role="customer")
            session.add_all([user, Subscription(account_id=account.id, plan_id="part")])
            session.commit()
            token = issue_development_token(user, settings)
        headers = {"Authorization": f"Bearer {token}"}
        payloads = [
            {"text": "draft a short note about this synthetic task", "idempotency_key": f"latency-{index:04d}"}
            for index in range(count + 2)
        ]

        def send(client: TestClient, payload: dict[str, str]) -> float:
            began = time.perf_counter()
            response = client.post("/v1/messages", headers=headers, json=payload)
            elapsed_ms = (time.perf_counter() - began) * 1000
            if response.status_code != 200 or response.json().get("route") != "fake-economy":
                raise RuntimeError(f"synthetic request failed: HTTP {response.status_code}")
            return elapsed_ms

        with TestClient(app) as client:
            for payload in payloads[:2]:
                send(client, payload)
            began = time.perf_counter()
            with ThreadPoolExecutor(max_workers=4) as pool:
                durations = list(pool.map(lambda payload: send(client, payload), payloads[2:]))
            wall_s = time.perf_counter() - began
            if hasattr(app.state, "telemetry") and app.state.telemetry is not None:
                app.state.telemetry.flush(timeout=10.0)
        engine.dispose()
    ordered = sorted(durations)
    return {
        "requests": count,
        "concurrency": 4,
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[min(count - 1, int(0.95 * count))], 2),
        "max_ms": round(ordered[-1], 2),
        "throughput_rps": round(count / wall_s, 2),
        "live_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="00b7224")
    parser.add_argument("--requests", type=int, default=24)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.requests < 8 or args.requests > 200:
        parser.error("requests must be between 8 and 200")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,100}", args.baseline_ref):
        parser.error("baseline-ref must be a safe Git ref")
    if args.source is not None:
        print(json.dumps(_benchmark(args.source.resolve(), args.requests), sort_keys=True))
        return
    git = shutil.which("git")
    if git is None:
        parser.error("git is required for baseline comparison")
    archived = subprocess.run(  # noqa: S603 - fixed git argv, validated ref, no shell
        [git, "archive", args.baseline_ref, "src/daily_agent"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    with tempfile.TemporaryDirectory(prefix="karmi-routing-baseline-") as directory:
        baseline = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as archive:
            archive.extractall(baseline, filter="data")
        def run(source: Path) -> dict[str, Any]:
            proc = subprocess.run(  # noqa: S603 - known interpreter and this script, no shell
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--source",
                    str(source),
                    "--requests",
                    str(args.requests),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(proc.stdout)
        before = run(baseline)
        after = run(ROOT)
    print(json.dumps({"baseline_ref": args.baseline_ref, "before": before, "after": after}, indent=2))


if __name__ == "__main__":
    main()
