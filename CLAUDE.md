# Daily Agent

Bounded, privacy-scoped assistant backend (FastAPI) with an owned web/PWA shell, plus an offline
model evaluation lab. Local development candidate: all plans, costs and users are synthetic.
Specification lives in `docs/blueprint/` (PRD, Architecture, Rules, Phases, Tier_Entitlements).

## Map

```
src/daily_agent/
  api.py        HTTP layer: all routes in create_app(); thin handlers
  services.py   business logic: budget reserve/settle/release, idempotent writes,
                note context, generation, inbox, run/outbox persistence
  providers.py  ONLY place allowed to import typesafe_sdk / call a live model
  models.py     SQLAlchemy models (money columns are BigInteger micro-units)
  plans.py      synthetic tier policies (ananta free / yanta / trika / part)
  config.py     Settings (DAILY_AGENT_* env); fails closed outside development/test
  security.py   dev tokens, principal/admin deps, HMAC webhook verification
  db.py         lazy engine (get_engine) + get_session dependency
  web/shell.py  inline HTML/JS shell served at /
src/model_lab/  offline benchmark CLI (typer) over SQLite; independent of daily_agent
migrations/     Alembic; env.py reads the DB URL from Settings
tests/          unit/, e2e/ (TestClient + temp SQLite), web/, model_lab/, integration/ (Docker)
```

Request flow for `POST /v1/messages`: idempotency check → `reserve_budget` → **commit** →
`build_note_context` + `fake_generate` (optional live provider calls) → `_apply_intent` →
`persist_completed_run` → `settle_budget` → commit. Any failure after reserve → `release_budget`.
A live duplicate request gets 409 (`ReservationInFlight`). Reservations left RESERVED past
`RESERVATION_LEASE_SECONDS` are reclaimed and charged as unknown cost.

## Commands

All gates go through `python scripts/tasks.py <task>` (Make targets delegate to it).

| Task | Command |
|---|---|
| Lint + secret scan | `python scripts/tasks.py lint` |
| Typecheck (mypy strict) | `python scripts/tasks.py typecheck` |
| Unit / web / model_lab | `python scripts/tasks.py test-unit` |
| API E2E | `python scripts/tasks.py test-e2e` |
| ModelLab demo | `python scripts/tasks.py benchmark-demo` |
| Postgres/Redis (needs Docker running) | `python scripts/tasks.py test-integration` |
| Everything | `python scripts/tasks.py test-release` |
| Dev server | `python scripts/tasks.py dev` → http://127.0.0.1:8000 |
| Regenerate lock (after editing deps) | `uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements.lock` |

Focused test: `python -m pytest tests/e2e/test_api.py -k <name>`. Use the `/verify` skill for the
full gate run with a summarized result.

## Engineering rules

- HTTP concerns stay in `api.py`; logic that touches money, idempotency or tenancy goes in `services.py`.
- Every query on user data is scoped by `account_id` (notes also by `owner_user_id`; tasks are
  account-shared by design).
- Idempotent writes: same key + same payload → replay; different payload → 409 via `_idempotency_conflict()`.
- New live-provider code goes only in `providers.py`, returns `ProviderCall`s, and its cost must
  flow through reserve → settle into `CostLedger`. Live models stay off unless `DAILY_AGENT_LIVE_MODELS_ENABLED=true`.
- Schema change = new Alembic migration + model change in the same commit; never edit an applied migration.
- Match existing style: ruff (line 100), mypy strict.

## Never

- Never enable WhatsApp, paid checkout, live charges, real outbound messages or production deploys.
- Never read, print or commit `.env` or real secrets; fixtures must stay obviously synthetic.
- Never weaken `Settings.fail_closed_in_production` or budget checks to make a test pass.
- Never mark Docker/integration, device, payment or provider checks as passed without running them.
- No force-push, history rewrites, `reset --hard`, or deleting untracked files (the root
  `test_hotrow.py` / `test_settlement.py` are the owner's scratch load tests: leave them alone).

## Definition of done

`lint`, `typecheck`, `test-unit`, `test-e2e` pass; money/concurrency changes also need
`test-integration` (or an explicit "NOT RUN: Docker unavailable"). Behavior changes carry a test.
Report VERIFIED / NOT VERIFIED separately.

## Other agents' files

`AGENTS.md`, `.codex/` and `Memory.md` belong to the Codex workflow. `Memory.md` is the running
state log. Read it when resuming a phase, but treat the code and git history as the source of truth.
Past audits live in `docs/reviews/`.
