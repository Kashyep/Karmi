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
            auth_secret="not-the-development-secret",
            webhook_secret="not-the-development-webhook-secret",
            paid_checkout_enabled=True,
        )


def test_production_rejects_known_webhook_placeholder() -> None:
    with pytest.raises(ValidationError, match="production webhook secret is unset"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://example.invalid/db",
            allow_development_auth=False,
            auth_secret="not-the-development-secret",
        )
