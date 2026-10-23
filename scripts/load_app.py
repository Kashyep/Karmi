"""Uvicorn entry point for the local SSE load test (development only).

    uvicorn load_app:app --app-dir scripts --workers 2 --no-access-log

Uvicorn re-imports the application in every worker process, so URL patching done in a parent
process is lost. This module applies the fake-provider wiring from ``dev_fake_provider`` itself,
BEFORE ``daily_agent.api`` is imported: fake OpenRouter URLs, the real-host httpx guard, and the
env defaults (only for variables that are unset). Nothing here talks to a real provider.

Environment (all optional, shell values win):
    FAKE_PROVIDER_PORT  port of the fake provider (default 8900)
    LOAD_APP_LOG_LEVEL  root log level (default INFO)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPTS_DIR.parent / "src"
for _path in (str(SRC_DIR), str(SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from dev_fake_provider import apply_fake_env_defaults, wire_fake_provider  # noqa: E402

apply_fake_env_defaults(os.environ)
wire_fake_provider()
logging.basicConfig(
    level=os.environ.get("LOAD_APP_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(process)d %(levelname)s %(name)s %(message)s",
)

from daily_agent.api import app  # noqa: E402

__all__ = ["app"]
