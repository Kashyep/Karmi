# SSE chat load test runbook

Scope: concurrent `POST /v1/chat/stream` requests against a local, scratch stack, measured by
`scripts/load_test_sse.py`. Development only. Nothing here talks to a real model provider, sends
messages to customers, or touches production data. Results are local evidence, not a production
capacity claim.

## What is measured (client side, per message)

- HTTP status of `POST /v1/chat/stream`.
- Time to first byte: elapsed time until the first SSE response body chunk. This is body-level, not
  the response status line.
- Time to first delta: elapsed time until the first `message.delta` event.
- Total duration: elapsed time until `run.finished` or `run.error`.
- Outcome: `finished`, `run_error` (terminal `run.error`), `http_error` (non-200 before the stream),
  `timeout` (per-message `--timeout`), `transport_error` (connection-level failure), or
  `no_terminal_event` (stream closed before a terminal event).
- Aggregates: counts by outcome and status, error rate, p50/p95/p99 of first-delta and total
  (computed over messages that produced that value), requests/s and successes/s, wall time, and
  peak concurrent open streams as counted by the client.
- Exit status: `0` when error rate is at most `--max-error-rate` (default `0.01`), `1` otherwise,
  `2` for bad input (for example duplicate principals or too few tokens).

## What is NOT measured

- No server-side metrics: database pool wait, query latency, per-worker CPU or memory, Redis
  latency. The script does not scrape `/metrics` or query Postgres. A pool-exhaustion failure appears
  only as an error outcome or status; the client cannot tell its cause.
- No real provider behaviour. Live models are ON, but OpenRouter is the fake OpenAI-compatible
  server from `scripts/dev_fake_provider.py fake` (port `FAKE_PROVIDER_PORT`, default 8900). The
  app's OpenRouter URLs are patched in `scripts/load_app.py` (`wire_fake_provider`); an httpx guard
  blocks any request to `openrouter.ai` or `typesafe.ai`. Fake latency and output are not
  representative of a real provider. The TypeSafe intent classifier is unconfigured (no
  `TYPESAFE_API_KEY`), so it is skipped, not faked.
- No reply-quality, correctness, resume, stop, continue or regenerate checks. The script sends only
  new messages.
- Clerk authentication is not exercised. Users authenticate with development tokens, so the Clerk
  verification cost is absent.
- No sustained-soak, memory-growth or long-duration behaviour: one message per user is the default
  and the run is short.
- Client and server share one machine. Client CPU and scheduling contend with the server, so the
  numbers are a lower bound on what a separate client host would show, not an absolute capacity.
- Redis is set but only backs the rate-limit window (shared through Redis when `redis_url` is set,
  per `src/daily_agent/config.py`) and background-task locks. Stream runs themselves are tracked
  in-process. Each uvicorn worker keeps its own stream registry.

## Prerequisites

- Python venv with the project installed: `/tmp/wt2-int/.venv/bin/python` (uses `httpx`, `alembic`,
  `uvicorn`, `psycopg`, `redis`).
- `/usr/bin/initdb`, `/usr/bin/pg_ctl`, `redis-server` on `PATH`.
- Run commands from the repository root with `PYTHONPATH=src` so `daily_agent` imports.
- Ports free: Postgres `55433`, Redis `56380`, API `8000`.

## 1. Scratch Postgres (`/tmp/m3-pg`, port 55433)

```bash
export PGDATA=/tmp/m3-pg
/usr/bin/initdb -D "$PGDATA" -U postgres -A trust --encoding=UTF8
/usr/bin/pg_ctl -D "$PGDATA" -l /tmp/m3-pg.log -w \
  -o "-p 55433 -c max_connections=300 -k $PGDATA" start
```

Database URL used below: `postgresql+psycopg://postgres@127.0.0.1:55433/postgres`.

## 2. Scratch Redis (port 56380)

```bash
redis-server --port 56380 --daemonize yes --save "" --appendonly no
```

## 3. Schema

```bash
export DAILY_AGENT_ENVIRONMENT=development
export DAILY_AGENT_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55433/postgres'
PYTHONPATH=src /tmp/wt2-int/.venv/bin/alembic upgrade head
```

## 4. Synthetic users and tokens (one distinct principal per virtual user)

`POST /dev/token` returns the same user for every call (it reuses the first user of a role), so
distinct principals must come from distinct `User` rows. The block below creates `LOAD_USERS`
accounts, each with its own subscription and customer user, and prints one development token per
user. Tokens are valid for one hour; mint them right before the run.

```bash
export LOAD_USERS=500
PYTHONPATH=src /tmp/wt2-int/.venv/bin/python - > /tmp/m3-tokens.txt <<'PY'
import os
import sys

from sqlalchemy.orm import Session

from daily_agent.config import get_settings
from daily_agent.db import get_engine
from daily_agent.models import Account, Subscription, User
from daily_agent.security import issue_development_token

settings = get_settings()
count = int(os.environ["LOAD_USERS"])
with Session(get_engine()) as session:
    for index in range(count):
        account = Account(name=f"load-test-{index}")
        session.add(account)
        session.flush()
        session.add(Subscription(account_id=account.id))
        user = User(account_id=account.id, display_name=f"Load user {index}", role="customer")
        session.add(user)
        session.flush()
        print(issue_development_token(user, settings, ttl_seconds=3600))
    session.commit()
print(f"seeded {count} users", file=sys.stderr)
PY
```

`/tmp/m3-tokens.txt` contains bearer secrets. Delete it after the run.

## 5. API server (fake provider, 2 workers)

```bash
export DAILY_AGENT_ENVIRONMENT=development
export DAILY_AGENT_DATABASE_URL='postgresql+psycopg://karmi@127.0.0.1:55433/m3load'
export DAILY_AGENT_REDIS_URL=redis://127.0.0.1:56380/0
export DAILY_AGENT_DATABASE_POOL_SIZE=20
export DAILY_AGENT_DATABASE_MAX_OVERFLOW=20
export DAILY_AGENT_RATE_LIMIT_PER_MINUTE=10000
export DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO=100000000
export DAILY_AGENT_GATEWAY_DAILY_REQUEST_LIMIT=1000000
export DAILY_AGENT_GATEWAY_PAID_RESERVED_REQUESTS=0
export FAKE_PROVIDER_PORT=8901
unset TYPESAFE_API_KEY
FAKE_PROVIDER_PORT=8901 /tmp/wt2-int/.venv/bin/python scripts/dev_fake_provider.py fake --port 8901 &
echo $! > /tmp/m3-fake.pid
cd /tmp/wt-m3 && PYTHONPATH=src /tmp/wt2-int/.venv/bin/uvicorn load_app:app --app-dir scripts \
  --host 127.0.0.1 --port 8765 --workers 2 --no-access-log &
echo $! > /tmp/m3-uvicorn.pid
```

`scripts/load_app.py` applies the fake-provider wiring and env defaults (unset variables only)
before importing `daily_agent.api`, so every worker gets it. Port 8765 is used because port 8000 is
taken on the test machine. `--no-access-log` is required: `install_log_redaction`
(`src/daily_agent/ratelimit.py`) drops `record.args`, which breaks access-log formatting.

Live models are on and OpenRouter is routed to the fake provider. OpenCode and paid checkout stay
disabled (their defaults). Development auth is only honoured when `DAILY_AGENT_ENVIRONMENT=development`.


Readiness check before loading: `curl -fsS http://127.0.0.1:8765/ready`.

Pool sizing: each worker opens at most `DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW` connections
(here 40), so 2 workers use at most 80 of the 300 Postgres connections. Pool waits longer than
`DATABASE_POOL_TIMEOUT` (default 15 s) surface as failed requests in the report.

## 6. Smoke test (one user)

```bash
/tmp/wt2-int/.venv/bin/python scripts/load_test_sse.py \
  --base-url http://127.0.0.1:8765 --tokens-file /tmp/m3-tokens.txt \
  --users 1 --ramp-seconds 0 --timeout 30
```

Expect `outcomes: {'finished': 1}`. Stop here if it fails.

## 7. Load run (500 users, one message each)

```bash
/tmp/wt2-int/.venv/bin/python scripts/load_test_sse.py \
  --base-url http://127.0.0.1:8765 --tokens-file /tmp/m3-tokens.txt \
  --users 500 --messages-per-user 1 --ramp-seconds 10 --timeout 120 \
  --max-error-rate 0.01 --json-out /tmp/m3-load-500.json
echo "exit=$?"
```

`--ramp-seconds` staggers user starts linearly across the ramp window. A ramp of 0 starts every
user at once; expect a higher peak of concurrent streams and more pool contention.

## 8. Teardown

```bash
kill "$(cat /tmp/m3-uvicorn.pid)" "$(cat /tmp/m3-fake.pid)"
# Stop Redis/Postgres only if this run started them (they were shared scratch services here).
rm -f /tmp/m3-tokens.txt
```

Keep `/tmp/m3-load-500.json` and the output of step 7 as the run record. The JSON holds per-message
samples (user index, outcome, status, timings, error category) and no tokens.

## Reporting

Record the command lines, git commit, the summary block printed by the script, and the exit code.
State the limits above with the result. Do not describe a run as a capacity or production result.

## Measured results (2026-10-24, local)

Setup: scratch Postgres on 127.0.0.1:55433 (database `m3load`, migrated to
head); Redis on 56380; fake OpenRouter on 8901; `uvicorn load_app:app --workers 2 --no-access-log`
on 8765; pool 20+20 per worker; `DAILY_AGENT_ENVIRONMENT=development`. Shared machine, client and
server on the same host. Client: `scripts/load_test_sse.py`, one message per user.

| Run | Users | Ramp | Finished | Errors | first delta p50 / p95 / p99 (s) | total p50 / p95 / p99 (s) | Wall (s) | req/s |
|---|---|---|---|---|---|---|---|---|
| Smoke | 3 | 0 | 3 | 0 | 0.139 / 0.186 / 0.186 | 0.279 / 0.325 / 0.325 | 0.33 | 9.13 |
| Load | 500 | 10 s | 500 | 0 (0.0000) | 0.024 / 0.047 / 0.082 | 0.155 / 0.186 / 0.223 | 10.14 | 49.32 |
| Burst | 500 | 0 | 140 | 360 `http_error` (HTTP 500), rate 0.72 | 75.74 / 76.98 / 77.21 (n=140) | 60.31 / 77.13 / 77.22 | 77.43 | 6.46 |

- Load run: time to first byte p50 0.017 s, p95 0.037 s, p99 0.058 s; peak concurrent streams 13
  (client-side). Exit 0.
- Burst run: exit 1 (above `--max-error-rate` 0.01). Server log: 362 tracebacks, each
  `sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 20 reached, connection timed out,
  timeout 15.00`. Cause: 500 simultaneous requests exceed the 80 pooled connections (2 workers ×
  40) and the 15 s pool wait. The 500 responses are pool-exhaustion failures, not provider failures.
  Peak concurrent streams 500 (client-side).
- Zero HTTP 429 and zero HTTP 402 in either run. Zero `Traceback` in the load run.
- Postgres connections for `m3load` sampled after the burst: 41 (a post-run sample, not the peak;
  peak was not sampled).
- Not measured: server CPU/memory, Redis latency, and peak Postgres connections during the burst.

Caveats: local, shared machine, development auth, fake OpenRouter (not a real provider), one message
per user. Not a capacity or production claim. A ramp of 10 s held 500 concurrent users with no
errors; an instantaneous 500-user burst with the current 80-connection pool does not.
