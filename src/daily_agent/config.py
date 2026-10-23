import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import certifi
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

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


def clerk_verification_config_valid(issuer: str | None, key_b64: str | None) -> bool:
    if not issuer or not key_b64:
        return False
    parsed_issuer = urlparse(issuer)
    if parsed_issuer.scheme != "https" or not parsed_issuer.netloc:
        return False
    try:
        key_data = base64.b64decode(key_b64, validate=True)
        public_key = load_pem_public_key(key_data)
    except (ValueError, binascii.Error, TypeError):
        return False
    return isinstance(public_key, RSAPublicKey)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DAILY_AGENT_", env_file=".env", extra="ignore", populate_by_name=True
    )

    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./data/development.db"
    migration_database_url: str | None = None
    # Per-process pool. Total DB connections = replicas * WEB_CONCURRENCY * (size + overflow);
    # keep that under the Neon pooler client limit / compute max_connections (docs/runbooks/scale.md).
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=15, ge=1, le=120)
    database_connect_timeout: int = Field(default=15, ge=1, le=120)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86_400)
    redis_url: str | None = None
    # Redis calls fail open after this timeout; the in-process fallbacks take over.
    redis_socket_timeout_seconds: float = Field(default=0.25, gt=0, le=10)
    auth_secret: str = "development-only-change-me"
    webhook_secret: str = "development-webhook-only"
    allow_development_auth: bool = True
    clerk_publishable_key: str | None = None
    clerk_issuer: str | None = None
    clerk_jwt_public_key_b64: str | None = None
    live_models_enabled: bool = False
    opencode_enabled: bool = False
    opencode_api_key: str | None = Field(default=None, repr=False)
    openrouter_enabled: bool = False
    # Also accepts the bare OPENROUTER_API_KEY used by the ignored ``.env.openrouter`` file.
    openrouter_api_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "DAILY_AGENT_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "OPEN_ROUTER_KEY"
        ),
    )
    # Emergency stop for every live model call; replies fall back to the deterministic demo.
    gateway_kill_switch: bool = False
    # Reviewed model-registry.v1 JSON; ``None`` loads the packaged seed registry.
    model_registry_path: Path | None = None
    gateway_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    gateway_breaker_failure_threshold: int = Field(default=5, ge=1, le=100)
    gateway_breaker_open_seconds: float = Field(default=60.0, gt=0)
    gateway_model_cooldown_seconds: float = Field(default=60.0, gt=0)
    # Shared daily cap on live provider requests across every account, matching the provider
    # key's own limit. The unfunded OpenRouter key allows 50 a day, so the default stays 50.
    # Raise it to the provider's real limit once the key is funded. The last
    # ``gateway_paid_reserved_requests`` of them are kept for paid plans, so the reserve must
    # stay strictly smaller than this limit. See docs/runbooks/scale.md.
    gateway_daily_request_limit: int = Field(default=50, ge=1)
    gateway_paid_reserved_requests: int = Field(default=10, ge=0)
    # Per-user cap on message/feedback/regenerate calls. Shared through Redis when redis_url is
    # set; otherwise each process enforces its own window (see daily_agent.ratelimit).
    rate_limit_per_minute: int = Field(default=30, ge=1, le=10_000)
    # Retention purge: deletes rows older than the per-table age below, in batches, on a timer.
    retention_purge_enabled: bool = True
    retention_purge_interval_seconds: int = Field(default=3600, ge=60, le=86_400)
    retention_batch_size: int = Field(default=1000, ge=1, le=100_000)
    retention_runs_days: int = Field(default=90, ge=1, le=3650)
    retention_ledger_days: int = Field(default=400, ge=1, le=3650)
    retention_routing_days: int = Field(default=90, ge=1, le=3650)
    retention_outbox_days: int = Field(default=30, ge=1, le=3650)
    retention_inbox_days: int = Field(default=30, ge=1, le=3650)
    # How often the budget-reservation sweeper runs, and how stale a run heartbeat may be
    # before the run is treated as interrupted.
    reservation_sweep_interval_seconds: int = Field(default=30, ge=5, le=3600)
    run_stale_seconds: int = Field(default=120, ge=10, le=3600)
    # Response compression. Server-sent event streams are never compressed.
    gzip_enabled: bool = True
    gzip_min_size: int = Field(default=1024, ge=0, le=1_048_576)
    # SSE output is flushed at most this often, or once this many characters are buffered.
    stream_flush_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    stream_flush_chars: int = Field(default=4096, ge=1, le=1_000_000)
    paid_checkout_enabled: bool = False
    whatsapp_enabled: bool = False
    # Beta access-code hashes (sha256 -> plan id); ``None`` loads the packaged file.
    access_codes_path: Path | None = None
    production_period_budget_micro: int | None = Field(default=None, ge=1)
    global_daily_budget_micro: int = Field(default=100_000, ge=1)
    data_dir: Path = Path("data")
    # Clerk subjects (user_...) allowed to open an admin session; comma-separated in the env.
    # Empty: nobody is an admin, whatever their role column says.
    admin_clerk_user_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("ADMIN_CLERK_USER_IDS", "DAILY_AGENT_ADMIN_CLERK_USER_IDS"),
    )
    # Budget-unit micros per displayed "USD" in the admin API (1:1 keeps the stored unit visible).
    admin_micro_per_usd: int = Field(default=1_000_000, ge=1)
    # Hex Ed25519 public keys whose PolicyBundleV1 signatures Karmi accepts. Empty: none.
    parakh_trusted_public_keys: list[str] = Field(default_factory=list)

    @field_validator("admin_clerk_user_ids", mode="before")
    @classmethod
    def split_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("database_url", "migration_database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None if value == "" else value
        try:
            url = make_url(value)
        except Exception:
            raise ValueError("invalid database URL") from None
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+psycopg")
        if url.host and url.host.endswith(".neon.tech"):
            # libpq validates both the certificate chain and endpoint hostname.
            url = url.update_query_dict({"sslmode": "verify-full", "sslrootcert": certifi.where()})
        return url.render_as_string(hide_password=False)

    @property
    def migration_url(self) -> str:
        url = self.migration_database_url or self.database_url
        host = make_url(url).host or ""
        if host.endswith(".neon.tech") and "-pooler" in host.split(".")[0]:
            raise ValueError("Neon migrations require a separate direct migration_database_url")
        return url

    @property
    def is_development(self) -> bool:
        return self.environment in DEVELOPMENT_ENVIRONMENTS

    @model_validator(mode="after")
    def fail_closed_in_production(self) -> "Settings":
        if bool(self.clerk_issuer) != bool(self.clerk_jwt_public_key_b64):
            raise ValueError("Clerk issuer and JWT verification key must be configured together")
        if (
            self.clerk_issuer
            and self.clerk_jwt_public_key_b64
            and not clerk_verification_config_valid(
                self.clerk_issuer, self.clerk_jwt_public_key_b64
            )
        ):
            raise ValueError("Clerk JWT verification configuration is invalid")
        if not self.is_development:
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires PostgreSQL")
            if self.allow_development_auth:
                raise ValueError("development authentication must be disabled in production")
            if _is_unsafe_production_secret(self.auth_secret):
                raise ValueError("production authentication secret is unset")
            if _is_unsafe_production_secret(self.webhook_secret):
                raise ValueError("production webhook secret is unset")
            if not self.clerk_issuer or not self.clerk_jwt_public_key_b64:
                raise ValueError("production Clerk JWT verification is unset")
            if self.paid_checkout_enabled and self.production_period_budget_micro is None:
                raise ValueError("paid checkout requires an approved finite period budget")
            if self.live_models_enabled and self.production_period_budget_micro is None:
                raise ValueError("live models require an approved finite period budget")
        if self.gateway_paid_reserved_requests >= self.gateway_daily_request_limit:
            raise ValueError("the paid reserve must leave some daily requests for the free plan")
        if self.whatsapp_enabled:
            raise ValueError("WhatsApp is policy-disabled for the current India-first release")
        if self.opencode_enabled and not self.opencode_api_key:
            raise ValueError("OpenCode is enabled but its API key is unset")
        if self.openrouter_enabled and not self.openrouter_api_key:
            raise ValueError("OpenRouter is enabled but its API key is unset")
        if (
            (self.opencode_enabled or self.openrouter_enabled)
            and not self.is_development
            and self.production_period_budget_micro is None
        ):
            raise ValueError("live model providers require an approved finite period budget")
        return self


@lru_cache
def get_settings() -> Settings:
    # Clerk's local dashboard values live separately from the main app config;
    # only the runtime loader opts into reading that private file.
    settings = Settings(  # type: ignore[call-arg]
        _env_file=(".env", ".env.clerk", ".env.opencode", ".env.openrouter")
    )
    # Only local SQLite-backed environments need a writable data directory; creating it
    # unconditionally breaks production containers with read-only filesystems.
    if settings.database_url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
