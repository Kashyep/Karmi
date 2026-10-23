# Scale runbook: 500 concurrent SSE chats

This runbook covers sizing the API for about 500 concurrent streaming chats, the settings that
control it, and how to verify a deployment. All settings use the `DAILY_AGENT_` prefix.

## Connection budget

Each uvicorn worker holds its own SQLAlchemy pool. Every replica therefore opens:

```
total_db_connections = replicas * WEB_CONCURRENCY * (DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW)
```

The Postgres server (or Neon pooler) must allow more connections than this total, with headroom
for migrations and operators.

Recommended starting point for 500 concurrent chats:

| Setting | Value | Why |
|---|---|---|
| `WEB_CONCURRENCY` | `4` per replica | Event loop per core; SSE holds a worker thread-free but DB sessions are per request. |
| `DAILY_AGENT_DATABASE_POOL_SIZE` | `10` | Default. |
| `DAILY_AGENT_DATABASE_MAX_OVERFLOW` | `10` | Default. |
| `DAILY_AGENT_DATABASE_POOL_TIMEOUT` | `15` | Seconds to wait for a pooled connection before failing fast. |
| `DAILY_AGENT_DATABASE_POOL_RECYCLE_SECONDS` | `1800` | Recycles connections before idle-timeout proxies drop them. |

With 2 replicas, 4 workers, and pool 10+10, the total is 160 connections. Size `max_connections`
(or the pooler limit) above that.

## Database

- Runtime traffic should use the Neon pooled host (`-pooler` in the hostname) via
  `DAILY_AGENT_DATABASE_URL`.
- Migrations need a direct connection. Set `DAILY_AGENT_MIGRATION_DATABASE_URL` to the direct
  host. Neon migrations refuse to run without it.
- The load-test Postgres in `compose.yaml` (profile `load`, port 55433) sets
  `max_connections=300`.

## Redis (shared rate limits and stream fan-out)

Set `DAILY_AGENT_REDIS_URL` to share rate limits and SSE event fan-out across replicas. Without
it, limits are per process and events are not mirrored.

- `DAILY_AGENT_REDIS_SOCKET_TIMEOUT_SECONDS` (default `0.25`) bounds every Redis call. A Redis
  outage degrades to in-process behavior and logs a warning at most once per minute. It does
  not fail requests.
- The load-test Redis (profile `load`, port 56380) sets `--maxclients 10000`.

## Rate limits and provider budget

- `DAILY_AGENT_RATE_LIMIT_PER_MINUTE` (default `30`) caps message, feedback, and regenerate
  calls per user.
- Access-code redemption is capped at 5 attempts per minute per user (fixed).
- `DAILY_AGENT_GATEWAY_DAILY_REQUEST_LIMIT` (default `50`) matches the currently unfunded
  provider key. Raise it when the key is funded. Keep the paid reserve
  (`gateway_paid_reserved_requests`) smaller than the daily limit; the config rejects the reverse.

## Streaming and responses

- `DAILY_AGENT_STREAM_FLUSH_INTERVAL_SECONDS` (default `2.0`) and
  `DAILY_AGENT_STREAM_FLUSH_CHARS` (default `4096`) control how often partial text is persisted.
- `DAILY_AGENT_GZIP_ENABLED` (default `true`) and `DAILY_AGENT_GZIP_MIN_SIZE` (default `1024`)
  control response compression. `text/event-stream` responses are never compressed, so tokens are
  not buffered.
- `UVICORN_LIMIT_CONCURRENCY` (container env, default `1000`) caps in-flight requests per worker.
  Excess connections receive 503 instead of queueing.
- Input size: every endpoint that accepts user text (`/v1/messages`, `/v1/runs/{id}/regenerate`,
  `/v1/chat/stream`, continue and regenerate, `/v1/tasks`, `/v1/reminders`, conversation title
  updates) rejects text above the plan's input budget with HTTP `413` and
  `{"detail": {"code": "INPUT_TOO_LARGE", "max_input_tokens": n}}` before any budget is reserved.
  Tokens are estimated at 4 UTF-8 bytes each.
- `Idempotency-Key` (optional header, 1-120 characters) on `POST /v1/messages/{id}/continue` and
  `POST /v1/messages/{id}/regenerate`. A repeat with the same key replays the run that key created,
  even after it finished, and reserves nothing. Different keys create separate continuations or
  variants. Without the header, the server-derived key applies as before.

## Background maintenance

These run inside each API process when `DAILY_AGENT_RETENTION_PURGE_ENABLED` is true.

| Setting | Default | Meaning |
|---|---|---|
| `RETENTION_PURGE_ENABLED` | `true` | Master switch for the purge loop. |
| `RETENTION_PURGE_INTERVAL_SECONDS` | `3600` | Loop period. |
| `RETENTION_BATCH_SIZE` | `1000` | Rows deleted per statement, to keep locks short. |
| `RETENTION_RUNS_DAYS` | `90` | Run history. |
| `RETENTION_LEDGER_DAYS` | `400` | Budget ledger (kept longer for audit). |
| `RETENTION_ROUTING_DAYS` | `90` | Routing evidence. |
| `RETENTION_OUTBOX_DAYS` | `30` | Delivered outbox rows. |
| `RETENTION_INBOX_DAYS` | `30` | Processed inbox rows. |
| `RESERVATION_SWEEP_INTERVAL_SECONDS` | `30` | How often stale budget reservations are released. |
| `RUN_STALE_SECONDS` | `120` | A run with no heartbeat for this long is marked interrupted on startup and by the sweep. |

## Verifying a deployment

1. `GET /health` returns `alive`, and `GET /ready` returns `ready`.
2. Check that `Content-Encoding: gzip` appears on a JSON response with `Accept-Encoding: gzip`,
   and is absent on a `text/event-stream` response.
3. Run `scripts/load_test_sse.py` against the load profile. Confirm that `max_connections` is not
   exceeded (`SELECT count(*) FROM pg_stat_activity;`).

## Settings reference (new in this change)

| Env var | Default | Notes |
|---|---|---|
| `DAILY_AGENT_DATABASE_POOL_SIZE` | `10` (1–100) | Per worker. |
| `DAILY_AGENT_DATABASE_MAX_OVERFLOW` | `10` (0–100) | Per worker. |
| `DAILY_AGENT_DATABASE_POOL_TIMEOUT` | `15` | Seconds. |
| `DAILY_AGENT_DATABASE_POOL_RECYCLE_SECONDS` | `1800` | Seconds. |
| `DAILY_AGENT_REDIS_SOCKET_TIMEOUT_SECONDS` | `0.25` | Seconds. |
| `DAILY_AGENT_RETENTION_*` | see table above | Retention windows and purge loop. |
| `DAILY_AGENT_RESERVATION_SWEEP_INTERVAL_SECONDS` | `30` | |
| `DAILY_AGENT_RUN_STALE_SECONDS` | `120` | |
| `DAILY_AGENT_GZIP_ENABLED` | `true` | |
| `DAILY_AGENT_GZIP_MIN_SIZE` | `1024` | Bytes. |
| `DAILY_AGENT_STREAM_FLUSH_INTERVAL_SECONDS` | `2.0` | Seconds. |
| `DAILY_AGENT_STREAM_FLUSH_CHARS` | `4096` | Characters. |
| `WEB_CONCURRENCY` | `2` (image default) | Uvicorn workers per replica. |
| `UVICORN_LIMIT_CONCURRENCY` | `1000` | In-flight requests per worker. |
