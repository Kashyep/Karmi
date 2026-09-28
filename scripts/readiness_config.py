#!/usr/bin/env python3
"""Read-only production configuration audit against Karmi's actual Settings and routes."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from daily_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def parse_env(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if separator and key.startswith("DAILY_AGENT_"):
            values[key.removeprefix("DAILY_AGENT_").lower()] = value.strip().strip("'\"")
    return values


def inspect(values: dict[str, str]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    def add(name: str, ok: bool | None, reason: str) -> None:
        checks.append({"id": name, "status": "PASS" if ok is True else "BLOCKED" if ok is None else "FAIL",
                       "reason": reason})
    add("environment", values.get("environment") == "production", "production environment explicitly selected")
    database = values.get("database_url", "")
    add("postgresql", database.startswith("postgresql+psycopg://") and not any(
        marker in database.lower() for marker in ("test", "demo", "development", "sqlite")),
        "production PostgreSQL URL, not a test/fixture database")
    add("development_auth", values.get("allow_development_auth", "true").lower() == "false",
        "development token issuance disabled")
    for secret in ("auth_secret", "webhook_secret"):
        val = values.get(secret, "")
        add(secret, len(val) >= 32 and not any(marker in val.lower() for marker in
            ("change-me", "development", "example", "fixture", "placeholder", "replace-for", "sample", "test-secret")),
            f"{secret} configured and not a documented placeholder (value never emitted)")
    period = values.get("production_period_budget_micro", "")
    global_budget = values.get("global_daily_budget_micro", "")
    add("period_budget", period.isdecimal() and int(period) > 0,
        "explicit finite approved production period budget")
    add("global_budget", global_budget.isdecimal() and int(global_budget) > 0,
        "explicit finite approved daily global ceiling")
    add("whatsapp", values.get("whatsapp_enabled", "false").lower() == "false",
        "WhatsApp feature remains disabled pending channel eligibility")
    add("development_endpoint", values.get("allow_development_auth", "true").lower() == "false",
        "/dev/token exists in API but must return 404 in production")
    add("public_https", values.get("public_base_url", "").startswith("https://"),
        "public base URL must use HTTPS; TLS termination requires separate observation")
    add("cors", values.get("cors_origins") != "*" and values.get("allowed_hosts") != "*",
        "no wildcard CORS or host allowlist")
    add("bind", values.get("host") not in {"0.0.0.0", "::", "*"},  # noqa: S104 - detects, never binds
        "no unrestricted direct application bind; inspect proxy configuration separately")
    add("no_debug", values.get("debug", "false").lower() == "false", "debug disabled")
    add("no_live_charge", values.get("paid_checkout_enabled", "false").lower() == "false" and
        values.get("live_models_enabled", "false").lower() == "false",
        "no unapproved live provider/payment traffic")
    add("synthetic_provider_disabled", False,
        "Karmi's current message handler falls back to fake_generate; no production cutover exists")
    add("production_auth", False,
        "only development HMAC tokens are implemented; no verified production identity provider")
    add("shadow_not_active", values.get("active_policy_mode", "static").lower() not in ("shadow", "synthetic"),
        "shadow policy cannot serve active production traffic")
    add("telemetry_live_observed", None, "requires deployed routing/usage traces with retention review")
    add("migrations_restored", None, "requires isolated Postgres upgrade/restore rehearsal")
    add("rollback_proven", None, "requires candidate-matched rollback observation")
    add("health_ready", (ROOT / "src/daily_agent/api.py").is_file(),
        "source exists; deployed /health and /ready still require live observations")
    add("tls_termination", None, "certificate, proxy and network boundary not available offline")
    add("payment_approval", None, "merchant eligibility and sandbox lifecycle need separate review")
    try:
        # Do not fill absent candidate fields from the operator's ambient environment.
        with patch.dict(os.environ, {}, clear=True):
            Settings(_env_file=None, **{k: v for k, v in values.items() if k in Settings.model_fields})
        add("settings_validator", True, "Karmi's production Settings validator accepted the typed input")
    except (ValidationError, ValueError, TypeError):
        # Formatted validation errors may contain secret values: never serialize them.
        add("settings_validator", False, "Karmi Settings validation rejected production configuration")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="explicit private production candidate config; never emitted")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.env_file is not None and not args.env_file.is_file():
        print("Production candidate config not found", file=sys.stderr)
        return 1
    values = parse_env(args.env_file)
    checks = inspect(values)
    status = "FAIL" if any(row["status"] == "FAIL" for row in checks) else (
        "BLOCKED" if any(row["status"] == "BLOCKED" for row in checks) else "PASS")
    result = {"schema_version": 1, "candidate_config_provided": args.env_file is not None,
              "status": status, "production_ready": False, "checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Karmi production configuration: {status}; no secret values recorded")
    return 0 if status == "PASS" else 1 if status == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
