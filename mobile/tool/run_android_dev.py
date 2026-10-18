"""Run Flutter with Clerk's publishable key read from the ignored local env."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"
ENV_FILE = ROOT / ".env.clerk"
PUBLISHABLE_NAME = "DAILY_AGENT_CLERK_PUBLISHABLE_KEY"


def read_publishable_key() -> str:
    if not ENV_FILE.is_file() or ENV_FILE.is_symlink():
        raise SystemExit("Missing private .env.clerk. Run: python scripts/setup_clerk.py")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name == PUBLISHABLE_NAME:
            key = ast.literal_eval(value)
            if isinstance(key, str) and key.startswith(("pk_test_", "pk_live_")):
                return key
    raise SystemExit(".env.clerk has no valid Clerk publishable key; rerun Clerk setup.")


def main() -> int:
    key = read_publishable_key()
    flutter_args = sys.argv[1:] or ["run"]
    command = [
        "flutter",
        *flutter_args,
        f"--dart-define=CLERK_PUBLISHABLE_KEY={key}",
    ]
    return subprocess.run(command, cwd=MOBILE, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
