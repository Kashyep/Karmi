from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def fail_closed_in_production(self) -> "Settings":
        if self.environment == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires PostgreSQL")
            if self.allow_development_auth:
                raise ValueError("development authentication must be disabled in production")
            if self.auth_secret == "development-only-change-me":
                raise ValueError("production authentication secret is unset")
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
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings

