from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    # Import this checkout's src/ even when the editable install points at another (worktrees).
    env = dict(os.environ if env is None else env)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH")]))
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)  # noqa: S603
    if completed.returncode:
        raise SystemExit(completed.returncode)


def doctor() -> None:
    print(f"python={sys.version.split()[0]}")
    print(f"workspace={ROOT}")
    print(f"docker={shutil.which('docker') or 'missing'}")
    print(f"git={shutil.which('git') or 'missing'}")
    if not (ROOT / "benchmarks" / "seed_cases.jsonl").exists():
        raise SystemExit("benchmark seed bank is missing")


def _podman_services() -> None:
    """Start disposable PostgreSQL/Redis with rootless podman (same images and ports as compose)."""
    run(["podman", "rm", "-f", "daily-agent-test-pg", "daily-agent-test-redis"])
    run([
        "podman", "run", "-d", "--name", "daily-agent-test-pg", "--network", "host",
        "-e", "POSTGRES_DB=daily_agent_test", "-e", "POSTGRES_USER=daily_agent_test",
        "-e", "POSTGRES_PASSWORD=daily_agent_test", "--tmpfs", "/var/lib/postgresql/data",
        "--health-cmd", "pg_isready -h 127.0.0.1 -p 55432 -U daily_agent_test -d daily_agent_test",
        "--health-interval", "2s", "docker.io/library/postgres:17-alpine",
        "postgres", "-c", "port=55432", "-c", "listen_addresses=127.0.0.1",
    ])
    run([
        "podman", "run", "-d", "--name", "daily-agent-test-redis", "--network", "host",
        "docker.io/library/redis:8-alpine", "redis-server", "--port", "56379", "--bind", "127.0.0.1",
        "--save", "", "--appendonly", "no",
    ])
    for _ in range(60):  # bounded wait for both services
        pg = subprocess.run(  # noqa: S603
            ["podman", "healthcheck", "run", "daily-agent-test-pg"],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if pg.returncode == 0:
            return
        time.sleep(1)
    raise SystemExit("disposable PostgreSQL did not become healthy")


def integration() -> None:
    use_docker = shutil.which("docker") is not None
    if not use_docker and shutil.which("podman") is None:
        raise SystemExit(
            "Docker or podman is required for disposable PostgreSQL/Redis integration tests "
            "(see docs/runbooks/local-development.md)"
        )
    env = os.environ.copy()
    env["DAILY_AGENT_INTEGRATION_DATABASE_URL"] = (
        "postgresql+psycopg://daily_agent_test:daily_agent_test@127.0.0.1:55432/daily_agent_test"
    )
    env["DAILY_AGENT_INTEGRATION_REDIS_URL"] = "redis://127.0.0.1:56379/15"
    if use_docker:
        run(["docker", "compose", "-p", "daily-agent-test", "up", "-d", "--wait", "postgres-test", "redis-test"])
    else:
        _podman_services()
    try:
        run([str(PYTHON), "-m", "pytest", "-m", "integration", "tests/integration"], env=env)
    finally:
        if use_docker:
            run(["docker", "compose", "-p", "daily-agent-test", "down", "--volumes"])
        else:
            run(["podman", "rm", "-f", "daily-agent-test-pg", "daily-agent-test-redis"])


def benchmark_demo() -> None:
    with tempfile.TemporaryDirectory(prefix="daily-agent-model-lab-") as directory:
        output = Path(directory)
        database = output / "demo.db"
        suite = "benchmarks/seed_cases.jsonl"
        run([str(PYTHON), "-m", "model_lab.cli", "suite", "validate", suite])
        run(
            [
                str(PYTHON),
                "-m",
                "model_lab.cli",
                "run",
                "--suite",
                suite,
                "--db",
                str(database),
                "--budget",
                "5",
                "--fail-every",
                "3",
            ]
        )
        for fmt in ("json", "csv", "md", "html", "svg"):
            run(
                [
                    str(PYTHON),
                    "-m",
                    "model_lab.cli",
                    "db-report",
                    "--suite",
                    suite,
                    "--db",
                    str(database),
                    "--out",
                    str(output / f"report.{fmt}"),
                    "--format",
                    fmt,
                ]
            )
        run(
            [
                str(PYTHON),
                "-m",
                "model_lab.cli",
                "router",
                "recommend",
                "--suite",
                suite,
                "--db",
                str(database),
                "--out",
                str(output / "router-draft.json"),
            ]
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Agent repository task runner")
    parser.add_argument(
        "task",
        choices=[
            "doctor",
            "dev",
            "worker",
            "lint",
            "typecheck",
            "test-unit",
            "test-e2e",
            "test-integration",
            "benchmark-demo",
            "test-smoke",
            "test-release",
        ],
    )
    task = parser.parse_args().task
    if task == "doctor":
        doctor()
    elif task == "dev":
        run([str(PYTHON), "-m", "uvicorn", "daily_agent.api:app", "--host", "127.0.0.1", "--port", "8000"])
    elif task == "worker":
        run([str(PYTHON), "-m", "daily_agent.worker"])
    elif task == "lint":
        run([str(PYTHON), "-m", "ruff", "check", "src", "tests", "scripts"])
        run([str(PYTHON), "scripts/secret_scan.py"])
    elif task == "typecheck":
        run([str(PYTHON), "-m", "mypy", "src"])
    elif task == "test-unit":
        run([str(PYTHON), "-m", "pytest", "tests/unit", "tests/model_lab", "tests/web"])
    elif task == "test-e2e":
        run([str(PYTHON), "-m", "pytest", "-m", "e2e or not integration", "tests/e2e"])
    elif task == "test-integration":
        integration()
    elif task == "benchmark-demo":
        benchmark_demo()
    elif task == "test-smoke":
        run([str(PYTHON), "-m", "pytest", "tests/e2e/test_api.py::test_message_dedupes_usage_and_persists_outbox"])
    elif task == "test-release":
        doctor()
        for name in ("lint", "typecheck", "test-unit", "test-e2e", "benchmark-demo"):
            run([str(PYTHON), str(Path(__file__).resolve()), name])
        integration()


if __name__ == "__main__":
    main()
