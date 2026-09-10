from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
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


def integration() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("Docker is required for disposable PostgreSQL/Redis integration tests")
    env = os.environ.copy()
    env["DAILY_AGENT_INTEGRATION_DATABASE_URL"] = (
        "postgresql+psycopg://daily_agent_test:daily_agent_test@127.0.0.1:55432/daily_agent_test"
    )
    env["DAILY_AGENT_INTEGRATION_REDIS_URL"] = "redis://127.0.0.1:56379/15"
    run(["docker", "compose", "-p", "daily-agent-test", "up", "-d", "--wait", "postgres-test", "redis-test"])
    try:
        run([str(PYTHON), "-m", "pytest", "-m", "integration", "tests/integration"], env=env)
    finally:
        run(["docker", "compose", "-p", "daily-agent-test", "down", "--volumes"])


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
