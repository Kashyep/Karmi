# Backend connection setup (Linux)

Run everything from `/home/rosso/Projects/Karmi` so the app loads the right `.env`.

```bash
cd /home/rosso/Projects/Karmi
python3 -m venv .venv
.venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
.venv/bin/python scripts/setup_backend.py
```

The setup prompts are hidden so pasted passwords do not appear in terminal history:

1. **Development PostgreSQL URL:** Enter uses the existing local SQLite path. To use PostgreSQL, create a separate development database with your database provider and paste its SQLAlchemy/psycopg connection URL, such as `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require`. Plain `postgresql://` URLs are converted automatically. URL-encode special characters in usernames/passwords, and preserve your provider's TLS parameters. Use a direct/session endpoint for migrations. Never use a production database.
2. **Development Redis URL:** Enter skips Redis. Otherwise paste `redis://USER:PASSWORD@HOST:6379/0` or `rediss://USER:PASSWORD@HOST:6379/0` for TLS. Redis is optional here; current workers process the SQL outbox, and `/ready` checks only the database.
3. Authentication and webhook secrets are generated automatically, saved in ignored `.env` with owner-only permissions, and never printed. There is no secret to paste into the mobile app.

Existing `.env` files are preserved. Edit an existing file locally rather than regenerating secrets: rotating the auth secret invalidates existing tokens. Ambient `DAILY_AGENT_*` environment variables override `.env`; remove stale overrides if configuration appears incorrect.

Before startup, apply migrations to your **development** database:

```bash
mkdir -p data
.venv/bin/python -m alembic upgrade head
.venv/bin/python scripts/tasks.py dev
```

An existing SQLite database originally created by the app rather than Alembic may report “table already exists”. Stop and reconcile its migration history against a backup; do not blindly stamp it or delete it. Fresh databases should always be migrated before the first app startup.

Database URLs for Neon: migrations need the **direct** Neon URL in `DAILY_AGENT_MIGRATION_DATABASE_URL`
(or the migration URL you pass to Alembic). A host containing `-pooler` is refused. The app runtime
uses the **pooled** URL through `DAILY_AGENT_DATABASE_URL`. `.env.neon` is never auto-loaded, so for
a local run against Neon, inject its values explicitly as environment variables for that command.
In production, use host secrets.

In another terminal:

```bash
cd /home/rosso/Projects/Karmi
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
.venv/bin/python scripts/tasks.py worker
```

Open `http://127.0.0.1:8000/` for the web shell or `/docs` for the API. The web/mobile development sign-in obtains a synthetic bearer token from `/dev/token`; it is not a production login. Keep the worker running for outbox/reminder processing; deliveries are test-adapter only.

## Connect the mobile app

Android emulator:

```bash
cd /home/rosso/Projects/Karmi/mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=KARMI_DEV_AUTH=true
```

USB-connected Android phone (with USB debugging and adb installed):

```bash
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=KARMI_DEV_AUTH=true
```

Repeat `adb reverse` after reconnecting the phone. The backend can stay bound to loopback. A desktop/iOS simulator can use `http://127.0.0.1:8000`. Restart the app after changing the compile-time URL.

## Remaining production work

This completes development connection configuration only. No cloud resources are created and no deployment or live provider call is performed. With OpenCode disabled (the default), general replies use the deterministic demo (`fake_generate`) and no API key is needed. The existing TypeSafe adapter scores notes/classifies intent. Pasting a model key alone will not make this a production AI backend.

The verified identity provider is wired in the backend and mobile client, but release still needs
the real-device sign-in/API journey, a real generation adapter with approved rates and finite
budgets, sandbox payment lifecycle verification, TLS hosting, database backup/restore and migration
rehearsal, monitoring, and candidate-matched release checks. Credentials for other services depend
on the selected providers; do not invent or paste them into chat. WhatsApp activation remains
blocked by the repository's channel gate. See `release-and-rollback.md` and
`scripts/readiness_config.py` for the existing release audit.

## Clerk development authentication

`scripts/setup_clerk.py` stores Clerk's publishable key, Frontend API issuer, and JWT PEM
verification key in ignored owner-only `.env.clerk`. `get_settings()` reads that file after
`.env`; test-created `Settings` instances do not implicitly read it. The backend needs no Clerk
Secret Key for session-token verification.

Clerk session tokens belong in the standard `Authorization: Bearer <token>` header. The backend
accepts RS256 session JWTs only when signature, issuer, expiry, issued-at time, and session ID
validate. It uses the immutable Clerk `sub` claim to find or create one Karmi customer. First login
creates a private account and an Ananta/free subscription; Clerk claims never grant admin access.
In local development, the existing `/dev/token` flow remains available. Production settings require
Clerk verification configuration and disable development tokens.

The Clerk subject link is stored in `users.clerk_subject`, which requires the additive migration
`1a2b3c4d5e6f`. It was applied to Neon after explicit approval. Neon is now at that revision, and the
helper verified the `clerk_subject` column and unique constraint. For future changes, first run
`alembic upgrade head` against a disposable local database; the Neon helper is pinned to this
reviewed revision and will refuse unexpected or partial schema states.

The Flutter app now presents a Karmi-styled email-code sign-in and sign-up screen, while Clerk
continues to handle identity verification and sessions. It sends a fresh Clerk session JWT with each
API request. The integration uses Clerk's Flutter package `0.0.18-beta`; the package is explicitly
marked beta and may have breaking changes before 1.0.0 ([package status](https://pub.dev/packages/clerk_flutter)).
The separate `/dev/token` path remains for local builds without Clerk configuration. No Clerk
Secret Key is used by the mobile app.

### Run the Clerk-configured app on the USB phone

The private `.env.clerk` already contains the publishable key and backend verification settings.
The helper reads only the publishable key for Flutter; it does not print or copy the PEM setting.
From the mobile project directory, with the Pixel unlocked and USB debugging authorized:

```bash
cd /home/rosso/Projects/Karmi/mobile
adb reverse tcp:8000 tcp:8000
python tool/run_android_dev.py run -d 5B271XEBF3XDF0 --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

`adb reverse` forwards the phone's loopback port to the computer's port 8000. Repeat it after
reconnecting USB. Start only the intended local backend; `.env.neon` is intentionally not loaded
and this mobile runbook does not start the app against Neon.

In the Clerk Dashboard, open the application associated with the saved `pk_test_` key, then open
**User & Authentication**. Enable email-code sign-in and email verification for sign-up. This
Karmi-owned screen currently supports email codes; password and external social sign-in are not
shown. Use your own test account on the phone; never paste its password or verification code into
chat. The orange **Development mode** label is expected while the test key is configured.

After the phone signs in, the app obtains a Clerk session JWT and the backend verifies it using the
saved public PEM. The first successful API request creates the local customer and free Ananta
subscription. Confirm the journey only after the backend is running and `/ready` succeeds. The
mobile install itself does not prove API-to-Neon connectivity or a production release.

## Model gateway (free OpenRouter / OpenCode Zen models)

Live chat replies go through `src/daily_agent/gateway/`. It is **off by default**: enable a provider
with `DAILY_AGENT_OPENROUTER_ENABLED=true` (key in the ignored `.env.openrouter` as
`OPENROUTER_API_KEY=...`) and/or `DAILY_AGENT_OPENCODE_ENABLED=true` (key in `.env.opencode`), and, in
production, a finite `DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO`. Models come from a reviewed
`model-registry.v1` file (`DAILY_AGENT_MODEL_REGISTRY_PATH`; the packaged seed covers the OpenCode free
models only). Only zero-price models load. Notes are attached only to drafting requests that point at
the user's notes, and only to models whose registry entry has `no_training` terms. A saved key alone
will not enable AI responses. With every provider off, or `DAILY_AGENT_GATEWAY_KILL_SWITCH=true`,
chat uses deterministic demo text and makes no network call. OpenRouter's free models are
rate-limited (20 requests/minute; 50/day without credits, 1000/day with at least $10 credits), so
per-tier daily request and token quotas, per-model cooldowns and a per-provider circuit breaker
apply; breaker/cooldown state is per process.

The offline ModelLab suite validates and scores imported results. `model_lab run-opencode` is the only
ModelLab path that calls the provider. It makes live calls only with `--allow-free-provider-requests`,
a saved key, and free-allowlist models. `--max-requests` caps all provider requests, including the
catalog check. Use synthetic prompts only. There is no best-model claim yet; a run is not a production
model selection.

When ready to prepare a key, create one from the official [OpenCode Zen dashboard](https://opencode.ai/zen).
The Zen catalog includes free models, but availability and free status can change; Zen may require
billing details, and requests can incur charges. Before any live test, set a small spend limit and
disable automatic reloading if available. Choose models only after reviewing the provider's data
policy: some free endpoints may use prompts to improve models, and the NVIDIA free endpoints prohibit
personal or confidential data. Use synthetic benchmark prompts only.

In a terminal, save the key without putting it in shell history or chat:

```bash
cd /home/rosso/Projects/Karmi
.venv/bin/python scripts/setup_opencode.py
```

Paste the API key at the hidden prompt. The helper saves it in ignored, owner-only `.env.opencode`,
preserves an existing file, and makes no provider request. Do not start a live benchmark until the
candidate set, data policies, and spend limit are reviewed.

## Production (Azure Container Apps)

- Secrets live in Azure Container Apps secrets. Container env vars reference them with `secretref:`.
  Never put real values in the image, the repo, a `.env` file, or chat. Placeholder only:
  `<set-in-host-secret-store>`.
- Required for production: `DAILY_AGENT_ENVIRONMENT=production`; a PostgreSQL
  `DAILY_AGENT_DATABASE_URL` (pooled runtime URL); Clerk issuer and JWT verification key set together;
  separate `DAILY_AGENT_AUTH_SECRET` and `DAILY_AGENT_WEBHOOK_SECRET` values, each a unique 64-hex
  secret (at least 32 characters, no placeholder text); `DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH=false`;
  finite budgets (`DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO`, `DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO`).
- Migrations run with the direct URL in `DAILY_AGENT_MIGRATION_DATABASE_URL`, never the pooled one.
- These stay disabled: WhatsApp, paid checkout, live models, and OpenCode.
- `scripts/readiness_config.py` intentionally reports `production_ready=false`. This section lists
  required configuration. It is not a production-ready claim.

Running `alembic upgrade head` from the container image builds the full production `Settings`, so the
migration job needs the same Clerk, auth/webhook secret and budget values as the API, plus
`DAILY_AGENT_MIGRATION_DATABASE_URL` (direct Neon URL). Alternatively run
`scripts/apply_neon_migrations.py` from a trusted host. The image contains no migration helper scripts.
