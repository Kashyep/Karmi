# Neon connection checkpoint

Step 6: operator reported successful read-only pooled connection to neondb, PostgreSQL 18.6 on 2026-10-10. This is operator evidence; the agent has not received credentials or accessed Neon.

Step 7: prepare private configuration:

```bash
cd /home/rosso/Projects/Karmi
.venv/bin/python -m scripts.setup_neon
```

In Neon Connect, copy the pooled URL with pooling ON for the first hidden prompt, then the direct URL with pooling OFF for the second. Use the existing production branch and neondb database. The script checks matching endpoints and saves owner-only, ignored `.env.neon`, preserving `.env`. It makes no network calls or database changes. Stop on setup error; share only the status line. Existing `.env.neon` files are preserved.

This file is deliberately not loaded automatically. Do not run app startup, worker or migrations using it yet. Review migration history, current schema and backups before authorizing database writes. Production auth and live model generation remain incomplete.

Implementation: runtime DAILY_AGENT_DATABASE_URL and separate DAILY_AGENT_MIGRATION_DATABASE_URL. PostgreSQL pool defaults: 2 connections, 0 overflow, 15-second pool wait and connection timeout, pre-ping. Limits apply per process; multiply by API processes/replicas and workers. Neon URLs normalize to psycopg and verify-full/system CA TLS. A compatible libpq and system trust store are required (local libpq 18.0.6 verified). Pooled Neon URLs are refused for migrations without a direct URL. SQLite defaults are preserved. PostgreSQL automatic create_all is disabled in API, worker and schema helper; reviewed Alembic migrations are required.

References: [Neon connection guidance](https://neon.com/docs/connect/connection-pooling), [Neon security](https://neon.com/docs/security/security-overview), [SQLAlchemy pool configuration](https://docs.sqlalchemy.org/en/20/core/pooling.html).

Local validation: 104 unit/E2E/web/ModelLab tests, lint/secret scan and source typecheck passed. Read-only Neon direct endpoint inventory with strict TLS passed. No production application startup, cloud integration tests or deployments performed.
