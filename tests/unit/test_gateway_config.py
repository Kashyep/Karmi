from pathlib import Path

import pytest

from daily_agent.config import Settings

BASE = {"environment": "test", "database_url": "sqlite+pysqlite:///:memory:"}


def test_enabled_openrouter_requires_a_key() -> None:
    with pytest.raises(ValueError, match="OpenRouter is enabled but its API key is unset"):
        Settings(**BASE, openrouter_enabled=True)


def test_enabled_opencode_requires_a_key() -> None:
    with pytest.raises(ValueError, match="OpenCode is enabled but its API key is unset"):
        Settings(**BASE, opencode_enabled=True)


def test_openrouter_key_is_read_from_the_bare_env_name_in_the_ignored_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env.openrouter"
    env_file.write_text("OPENROUTER_API_KEY=sk-or-synthetic\nDAILY_AGENT_OPENROUTER_ENABLED=true\n")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings(_env_file=str(env_file), **BASE)  # type: ignore[call-arg]
    assert settings.openrouter_api_key == "sk-or-synthetic"
    assert "sk-or-synthetic" not in repr(settings)


def test_production_requires_a_finite_budget_for_live_providers(clerk_public_key_b64: str) -> None:
    with pytest.raises(ValueError, match="live model providers require"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://example.invalid/db",
            allow_development_auth=False,
            auth_secret="a9f2c7e8b4d61093a5c8e2f7d1b40699",
            webhook_secret="7d3b9f1a6c2048e5b7d0a2c4f9e18365",
            clerk_issuer="https://example.clerk.accounts.dev",
            clerk_jwt_public_key_b64=clerk_public_key_b64,
            openrouter_enabled=True,
            openrouter_api_key="sk-or-synthetic",
        )


def test_paid_reserve_must_leave_free_requests() -> None:
    with pytest.raises(ValueError, match="paid reserve must leave"):
        Settings(**BASE, gateway_daily_request_limit=10, gateway_paid_reserved_requests=10)
    settings = Settings(**BASE)
    assert (settings.gateway_daily_request_limit, settings.gateway_paid_reserved_requests) == (
        50,
        10,
    )
