from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_MARKERS = (
    "change-me",
    "development",
    "example",
    "fixture",
    "placeholder",
    "replace-for",
    "sample",
    "test-secret",
)


def _is_unsafe_production_secret(value: str) -> bool:
    normalized = value.strip().lower()
    return len(normalized) < 32 or any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


DEVELOPMENT_ENVIRONMENTS = frozenset({"development", "test"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DAILY_AGENT_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./data/development.db"
    redis_url: str | None = None
    auth_secret: str = "development-only-change-me"
    webhook_secret: str = "development-webhook-only"
    allow_development_auth: bool = True
    live_models_enabled: bool = False
    paid_checkout_enabled: bool = False
    whatsapp_enabled: bool = False
    production_period_budget_micro: int | None = Field(default=None, ge=1)
    global_daily_budget_micro: int = Field(default=100_000, ge=1)
    data_dir: Path = Path("data")

    @property
    def is_development(self) -> bool:
        return self.environment in DEVELOPMENT_ENVIRONMENTS

    @model_validator(mode="after")
    def fail_closed_in_production(self) -> "Settings":
        if not self.is_development:
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires PostgreSQL")
            if self.allow_development_auth:
                raise ValueError("development authentication must be disabled in production")
            if _is_unsafe_production_secret(self.auth_secret):
                raise ValueError("production authentication secret is unset")
            if _is_unsafe_production_secret(self.webhook_secret):
                raise ValueError("production webhook secret is unset")
            if self.paid_checkout_enabled and self.production_period_budget_micro is None:
                raise ValueError("paid checkout requires an approved finite period budget")
            if self.live_models_enabled and self.production_period_budget_micro is None:
                raise ValueError("live models require an approved finite period budget")
        if self.whatsapp_enabled:
            raise ValueError("WhatsApp is policy-disabled for the current India-first release")
        return self


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Only local SQLite-backed environments need a writable data directory; creating it
    # unconditionally breaks production containers with read-only filesystems.
    if settings.database_url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
