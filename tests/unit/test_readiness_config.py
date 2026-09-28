"""Release scanner must expose defects without exposing credential values."""
from __future__ import annotations

import json

from scripts.readiness_config import inspect, parse_env


def outcome(values: dict[str, str], check_id: str) -> str:
    return next(row["status"] for row in inspect(values) if row["id"] == check_id)


def test_no_production_config_rejects_dev_auth_database_and_synthetic_route() -> None:
    checks = inspect({})
    statuses = {check["id"]: check["status"] for check in checks}
    assert statuses["postgresql"] == "FAIL"
    assert statuses["development_auth"] == "FAIL"
    assert statuses["synthetic_provider_disabled"] == "FAIL"
    assert statuses["production_auth"] == "FAIL"
    assert statuses["rollback_proven"] == "BLOCKED"


def test_explicit_insecure_config_rejects_public_http_wildcards_and_shadow() -> None:
    values = {"environment": "production", "public_base_url": "http://example.invalid",
              "cors_origins": "*", "host": "0.0.0.0", "active_policy_mode": "shadow"}  # noqa: S104
    for check in ("public_https", "cors", "bind", "shadow_not_active"):
        assert outcome(values, check) == "FAIL"


def test_candidate_secret_values_are_not_reported(tmp_path) -> None:
    secret = "canary-not-for-logs-" + "X" * 40
    config = tmp_path / "private.env"
    config.write_text("DAILY_AGENT_ENVIRONMENT=production\nDAILY_AGENT_AUTH_SECRET=" + secret + "\n")
    rendered = json.dumps(inspect(parse_env(config)))
    assert secret not in rendered
    assert outcome(parse_env(config), "webhook_secret") == "FAIL"


def test_secure_shaped_settings_still_cannot_pass_missing_product_capabilities() -> None:
    values = {"environment": "production", "database_url": "postgresql+psycopg://user@db.local/app",
              "allow_development_auth": "false", "auth_secret": "z" * 40,
              "webhook_secret": "y" * 40, "production_period_budget_micro": "12345",
              "global_daily_budget_micro": "54321", "public_base_url": "https://example.invalid"}
    assert outcome(values, "settings_validator") == "PASS"
    assert outcome(values, "synthetic_provider_disabled") == "FAIL"
    assert outcome(values, "production_auth") == "FAIL"
