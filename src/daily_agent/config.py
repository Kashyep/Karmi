from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    # Model routing (ADR-0003). ``static`` preserves the pre-router behaviour exactly.
    router_mode: Literal["static", "shadow", "bandit", "canary"] = "static"
    router_policy_dir: Path = Path("data/router_policies")
    # Base64 raw Ed25519 public key that signs PolicyBundleV1 artifacts. Required to load any.
    router_policy_public_key: str | None = None
    # Share of actors (0-100, stable hash buckets) served by the active bundle in canary mode.
    router_canary_percent: int = Field(default=0, ge=0, le=100)
    router_exploration_enabled: bool = False
    router_max_exploration_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    # Exploration is additionally limited to these explicit allowlists (empty = nowhere).
    router_exploration_tiers: list[str] = Field(default_factory=list)
    router_exploration_domains: list[str] = Field(default_factory=list)
    # An exploratory action may only pick a route whose expected cost is at most this.
    router_exploration_max_cost_micro: int = Field(default=0, ge=0)
    router_disabled_models: list[str] = Field(default_factory=list)
    router_reload_interval_seconds: float = Field(default=5.0, ge=0.0)
    router_circuit_failure_threshold: int = Field(default=5, ge=1)
    router_circuit_cooldown_seconds: float = Field(default=30.0, ge=0.0)
    # Automatic demotion of a learned live policy (bandit/canary) back to static.
    router_guardrails_enabled: bool = True
    router_guardrail_min_samples: int = Field(default=50, ge=1)
    router_guardrail_window: int = Field(default=200, ge=1)
    router_guardrail_max_failure_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    router_guardrail_max_fallback_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    router_guardrail_max_mean_cost_micro: int | None = Field(default=None, ge=1)
    router_guardrail_max_p95_latency_ms: int | None = Field(default=None, ge=1)

    # Telemetry (ADR-0003). Pseudonyms are keyed from ``auth_secret`` with domain separation.
    telemetry_enabled: bool = True
    telemetry_queue_size: int = Field(default=10_000, ge=10)
    telemetry_batch_size: int = Field(default=200, ge=1)
    telemetry_flush_interval_seconds: float = Field(default=1.0, gt=0.0)
    telemetry_spool_path: Path = Path("data/telemetry-spool.jsonl")
    telemetry_export_dir: Path = Path("data/telemetry-exports")
    telemetry_attribution_window_seconds: int = Field(default=86_400, ge=0)
    telemetry_retention_days: int = Field(default=90, ge=1)
    telemetry_store_correction_text: bool = False

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
            if self.router_mode != "static" and not self.router_policy_public_key:
                raise ValueError("learned routing requires a policy signature public key")
        if self.whatsapp_enabled:
            raise ValueError("WhatsApp is policy-disabled for the current India-first release")
        if self.router_exploration_enabled and self.router_mode not in {"bandit", "canary"}:
            raise ValueError("exploration requires router_mode bandit or canary")
        return self


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Only local SQLite-backed environments need a writable data directory; creating it
    # unconditionally breaks production containers with read-only filesystems.
    if settings.database_url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
