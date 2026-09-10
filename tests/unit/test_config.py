import pytest
from pydantic import ValidationError

from daily_agent.config import Settings


def test_production_configuration_fails_closed() -> None:
    with pytest.raises(ValidationError, match="production requires PostgreSQL"):
        Settings(environment="production")


def test_whatsapp_cannot_be_activated_for_current_release() -> None:
    with pytest.raises(ValidationError, match="policy-disabled"):
        Settings(whatsapp_enabled=True)


def test_paid_checkout_requires_finite_approved_budget() -> None:
    with pytest.raises(ValidationError, match="approved finite period budget"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://example.invalid/db",
            allow_development_auth=False,
            auth_secret="a9f2c7e8b4d61093a5c8e2f7d1b40699",
            webhook_secret="7d3b9f1a6c2048e5b7d0a2c4f9e18365",
            paid_checkout_enabled=True,
        )


def test_production_rejects_known_webhook_placeholder() -> None:
    with pytest.raises(ValidationError, match="production webhook secret is unset"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://example.invalid/db",
            allow_development_auth=False,
            auth_secret="a9f2c7e8b4d61093a5c8e2f7d1b40699",
        )


def test_production_rejects_documented_example_secret() -> None:
    with pytest.raises(ValidationError, match="production webhook secret is unset"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://example.invalid/db",
            allow_development_auth=False,
            auth_secret="a9f2c7e8b4d61093a5c8e2f7d1b40699",
            webhook_secret="replace-for-any-shared-environment",
        )


@pytest.mark.parametrize("field", ["auth_secret", "webhook_secret"])
def test_production_rejects_whitespace_only_secrets(field: str) -> None:
    values = {
        "environment": "production",
        "database_url": "postgresql+psycopg://example.invalid/db",
        "allow_development_auth": False,
        "auth_secret": "a9f2c7e8b4d61093a5c8e2f7d1b40699",
        "webhook_secret": "7d3b9f1a6c2048e5b7d0a2c4f9e18365",
    }
    values[field] = " " * 32
    with pytest.raises(
        ValidationError,
        match=f"production {'authentication' if field == 'auth_secret' else 'webhook'} secret is unset",
    ):
        Settings(**values)  # type: ignore[arg-type]
