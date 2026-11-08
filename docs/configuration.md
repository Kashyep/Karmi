# Configuration reference

Backend settings are defined by the `Settings` class in `src/daily_agent/config.py`. They are read
from environment variables with the prefix `DAILY_AGENT_` (for example `DAILY_AGENT_DATABASE_URL`),
from a `.env` file in the working directory, and, through `get_settings()`, from `.env.clerk`,
`.env.opencode` and `.env.openrouter` when present. Unknown variables are ignored.
[`.env.example`](../.env.example) is a template; copy it to `.env` and never commit the copy.

"Production" below means any `DAILY_AGENT_ENVIRONMENT` other than `development` or `test`. In that
case `Settings` refuses to start unless the "required" rules in the table hold.

## Settings

| Name | Default | Required in production | Secret? | Meaning |
|---|---|---|---|---|
| `DAILY_AGENT_ENVIRONMENT` | `development` | set it | no | Deployment name. Anything except `development`/`test` enables the production checks. |
| `DAILY_AGENT_DATABASE_URL` | `sqlite+pysqlite:///./data/development.db` | yes, PostgreSQL (SQLite is rejected) | yes (contains credentials) | SQLAlchemy URL. `postgres://` and `postgresql://` are rewritten to `postgresql+psycopg`. Neon hosts get `sslmode=verify-full` and a CA bundle. |
| `DAILY_AGENT_MIGRATION_DATABASE_URL` | unset | no | yes | Direct (non-pooled) URL used by Alembic. A Neon `-pooler` host is refused. Falls back to the database URL. |
| `DAILY_AGENT_DATABASE_POOL_SIZE` | `10` (1 to 100) | no | no | SQLAlchemy pool size per process. |
| `DAILY_AGENT_DATABASE_MAX_OVERFLOW` | `10` (0 to 100) | no | no | Extra connections beyond the pool per process. |
| `DAILY_AGENT_DATABASE_POOL_TIMEOUT` | `15` | no | no | Seconds to wait for a pooled connection. |
| `DAILY_AGENT_DATABASE_CONNECT_TIMEOUT` | `15` | no | no | Seconds to wait when opening a connection. |
| `DAILY_AGENT_DATABASE_POOL_RECYCLE_SECONDS` | `1800` | no | no | Recycle pooled connections after this many seconds. |
| `DAILY_AGENT_DATABASE_ADMISSION_WAIT_SECONDS` | `10.0` | no | no | How long a request waits for a database session slot before the API answers `DATABASE_BUSY` (503). |
| `DAILY_AGENT_REDIS_URL` | unset | no | yes (may contain a password) | Optional. Without it the API uses in-process state; with it, rate limits, maintenance locks and stream state are shared across workers. |
| `DAILY_AGENT_REDIS_SOCKET_TIMEOUT_SECONDS` | `0.25` | no | no | Redis socket timeout. Redis errors never fail a request. |
| `DAILY_AGENT_AUTH_SECRET` | `development-only-change-me` | yes: 32+ characters, no placeholder text | yes | Application authentication secret. |
| `DAILY_AGENT_WEBHOOK_SECRET` | `development-webhook-only` | yes: 32+ characters, no placeholder text | yes | HMAC secret that signs and verifies webhook payloads. |
| `DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH` | `true` | yes, must be `false` | no | Enables `POST /dev/token` development sign-in. |
| `DAILY_AGENT_CLERK_PUBLISHABLE_KEY` | unset | no | no (public by design) | Clerk publishable key, used by the admin page. |
| `DAILY_AGENT_CLERK_ISSUER` | unset | yes (https URL; set together with the key below) | no | Clerk issuer for verifying bearer tokens. |
| `DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64` | unset | yes (base64 RSA public key PEM) | no (public key) | Clerk JWT verification key. |
| `DAILY_AGENT_CLERK_SECRET_KEY` | unset | no | yes | Clerk Backend API key; only needed so admins can revoke a user's Clerk sessions. |
| `DAILY_AGENT_LIVE_MODELS_ENABLED` | `false` | no | no | Master switch for live model calls. |
| `DAILY_AGENT_OPENCODE_ENABLED` | `false` | no | no | Enable the OpenCode adapter (needs its key). |
| `DAILY_AGENT_OPENCODE_API_KEY` | unset | only if OpenCode is enabled | yes | OpenCode key. |
| `DAILY_AGENT_OPENROUTER_ENABLED` | `false` | no | no | Enable the OpenRouter adapter (needs its key). |
| `DAILY_AGENT_OPENROUTER_API_KEY` | unset | only if OpenRouter is enabled | yes | OpenRouter key. `OPENROUTER_API_KEY` and `OPEN_ROUTER_KEY` are also accepted. |
| `DAILY_AGENT_GATEWAY_KILL_SWITCH` | `false` | no | no | Stops every live model call; replies fall back to the deterministic demo copy. |
| `DAILY_AGENT_MODEL_REGISTRY_PATH` | unset | no | no | Path to a reviewed `model-registry.v1` file (zero-price models only). |
| `DAILY_AGENT_GATEWAY_TIMEOUT_SECONDS` | `20.0` | no | no | Per-attempt provider timeout. |
| `DAILY_AGENT_GATEWAY_BREAKER_FAILURE_THRESHOLD` | `5` | no | no | Consecutive failures before a provider circuit opens. |
| `DAILY_AGENT_GATEWAY_BREAKER_OPEN_SECONDS` | `60.0` | no | no | How long an open circuit stays open. |
| `DAILY_AGENT_GATEWAY_MODEL_COOLDOWN_SECONDS` | `60.0` | no | no | Cooldown for a model after a failure. |
| `DAILY_AGENT_GATEWAY_DAILY_REQUEST_LIMIT` | `50` | no | no | Shared provider requests per day; beyond it the API returns `429 BETA_CAPACITY_FULL`. |
| `DAILY_AGENT_GATEWAY_PAID_RESERVED_REQUESTS` | `10` (must be below the daily limit) | no | no | Part of the daily limit reserved for paid-plan users. |
| `DAILY_AGENT_RATE_LIMIT_PER_MINUTE` | `30` | no | no | Per-user request rate limit. |
| `DAILY_AGENT_PAID_CHECKOUT_ENABLED` | `false` | no | no | Paid checkout. Disabled for the beta; outside development it also needs the period budget below. |
| `DAILY_AGENT_WHATSAPP_ENABLED` | `false` | no | no | `true` is always rejected; WhatsApp is disabled. |
| `DAILY_AGENT_ACCESS_CODES_PATH` | unset (the packaged `daily_agent/data/access_codes.json` is used) | no | the file holds code hashes; keep it private | JSON file with SHA-256 hashes of beta access codes. |
| `DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO` | unset (at least 1 when set) | yes, when live models, OpenCode or OpenRouter are enabled outside development | no | Per-period spend budget in micro-rupees. |
| `DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO` | `100000` | no | no | Platform-wide daily budget in micro-rupees. |
| `DAILY_AGENT_DATA_DIR` | `data` | no | no | Directory for local data files. |
| `DAILY_AGENT_RETENTION_PURGE_ENABLED` | `true` | no | no | Enable the periodic retention purge. |
| `DAILY_AGENT_RETENTION_PURGE_INTERVAL_SECONDS` | `3600` | no | no | Seconds between purge passes. |
| `DAILY_AGENT_RETENTION_BATCH_SIZE` | `1000` | no | no | Rows deleted per transaction. |
| `DAILY_AGENT_RETENTION_RUNS_DAYS` | `90` | no | no | Days to keep runs. |
| `DAILY_AGENT_RETENTION_LEDGER_DAYS` | `400` | no | no | Days to keep ledger rows. |
| `DAILY_AGENT_RETENTION_ROUTING_DAYS` | `90` | no | no | Days to keep routing evidence. |
| `DAILY_AGENT_RETENTION_OUTBOX_DAYS` | `30` | no | no | Days to keep outbox rows. |
| `DAILY_AGENT_RETENTION_INBOX_DAYS` | `30` | no | no | Days to keep inbox rows. |
| `DAILY_AGENT_RESERVATION_SWEEP_INTERVAL_SECONDS` | `30` | no | no | Seconds between sweeps of stale budget reservations. |
| `DAILY_AGENT_RUN_STALE_SECONDS` | `120` | no | no | Age after which an unfinished run counts as stale. |
| `DAILY_AGENT_GZIP_ENABLED` | `true` | no | no | Response compression (never applied to event streams). |
| `DAILY_AGENT_GZIP_MIN_SIZE` | `1024` | no | no | Minimum response size in bytes to compress. |
| `DAILY_AGENT_STREAM_FLUSH_INTERVAL_SECONDS` | `2.0` | no | no | How often streamed text is persisted. |
| `DAILY_AGENT_STREAM_FLUSH_CHARS` | `4096` | no | no | Characters buffered before streamed text is persisted. |
| `ADMIN_CLERK_USER_IDS` or `DAILY_AGENT_ADMIN_CLERK_USER_IDS` | empty | no | no (identifiers) | Comma-separated Clerk user IDs allowed to use the admin API. |
| `ADMIN_UI_ENABLED` or `DAILY_AGENT_ADMIN_UI_ENABLED` | `true` | no | no | Serve the `/admin` dashboard; when `false` it returns 404. |
| `DAILY_AGENT_PARAKH_TRUSTED_PUBLIC_KEYS` | empty list (JSON array) | no | no (public keys) | Hex Ed25519 public keys whose signed policy bundles are accepted. |

## Read outside `Settings`

| Name | Default | Meaning |
|---|---|---|
| `DAILY_AGENT_CHAT_TIMING_ENABLED` | off (`1`, `true`, `yes` or `on` enable) | Per-request chat timing logs for local benchmarking (`src/daily_agent/chat_timing.py`). |

## Notes

- `.env.example` sets the pool to `2` and `0` ("keep these small" for the pooled Neon URL); the code
  defaults are `10` and `10`. Total connections are replicas x workers x (size + overflow), see
  [runbooks/scale.md](runbooks/scale.md).
- Outside development, enabling paid checkout, live models, OpenCode or OpenRouter is rejected
  unless `DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO` is set. Paid checkout stays disabled for the
  beta. Read `fail_closed_in_production` in `src/daily_agent/config.py` for the exact checks.
