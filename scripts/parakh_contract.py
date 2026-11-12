"""Check the Parakh exchange contract against a Parakh checkout.

Karmi never imports Parakh code. This check (1) requires the two TelemetryBatchV1 /
PolicyBundleV1 schema copies to be byte-identical and (2) runs Parakh's cross-repo test
under this interpreter with Karmi's ``src`` on the path, the same way Parakh's CI does.

Usage: ``PARAKH_DIR=../Parakh python scripts/tasks.py parakh-contract``
A missing Parakh checkout is an error, never a skip.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ("telemetry_batch_v1.schema.json", "policy_bundle_v1.schema.json")
CROSS_REPO_TEST = "tests/test_cross_repo_readiness.py"
# Forced off so the check can never reach a live model, WhatsApp or checkout.
SAFE_FLAGS = {
    "DAILY_AGENT_ENVIRONMENT": "test",
    "DAILY_AGENT_LIVE_MODELS_ENABLED": "false",
    "DAILY_AGENT_OPENROUTER_ENABLED": "false",
    "DAILY_AGENT_OPENCODE_ENABLED": "false",
    "DAILY_AGENT_WHATSAPP_ENABLED": "false",
    "DAILY_AGENT_PAID_CHECKOUT_ENABLED": "false",
}


def parakh_dir() -> Path:
    raw = os.environ.get("PARAKH_DIR")
    if not raw:
        raise SystemExit("PARAKH_DIR is not set: point it at a Parakh checkout (e.g. ../Parakh)")
    path = Path(raw).resolve()
    if not (path / CROSS_REPO_TEST).is_file() or not (path / "contracts").is_dir():
        raise SystemExit(f"PARAKH_DIR={path} is not a Parakh checkout (no {CROSS_REPO_TEST})")
    return path


def check_schemas(parakh: Path) -> None:
    for name in SCHEMAS:
        ours = (ROOT / "docs/contracts/parakh" / name).read_bytes()
        theirs = (parakh / "contracts" / name).read_bytes()
        if ours != theirs:
            raise SystemExit(
                f"schema drift: docs/contracts/parakh/{name} differs from Parakh contracts/{name}"
            )
        print(f"schema identical: {name}")


def run_cross_repo_test(parakh: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DAILY_AGENT_")}
    env.update(SAFE_FLAGS)
    env["PARAKH_REQUIRE_KARMI"] = "1"
    env["PARAKH_KARMI_DIR"] = str(ROOT)
    env["PYTHONPATH"] = os.pathsep.join([str(parakh), str(ROOT / "src")])
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", CROSS_REPO_TEST]
    print("+", " ".join(command), f"(cwd={parakh})", flush=True)
    completed = subprocess.run(command, cwd=parakh, env=env, check=False)  # noqa: S603
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> None:
    parakh = parakh_dir()
    check_schemas(parakh)
    run_cross_repo_test(parakh)


if __name__ == "__main__":
    main()
