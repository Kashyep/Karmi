---
paths:
  - "src/daily_agent/services.py"
  - "src/daily_agent/models.py"
  - "src/daily_agent/providers.py"
  - "src/daily_agent/api.py"
  - "migrations/**"
---

# Money, budget and tenancy invariants

- Money is integer **micro-units** in `BigInteger` columns. Never floats, never 32-bit.
- Budget counters (`UsageWindow`, `UsagePeriod`, `PlatformBudget`) change only via **conditional
  `UPDATE ... WHERE reserved+settled+amount <= limit`**, checking `rowcount == 1`. Never
  read-modify-write in Python: it races under Postgres concurrency.
- `settle_budget` / `release_budget` first *claim* the reservation (`status == RESERVED` →
  new status). Keep that claim first so concurrent settlers cannot double-apply.
- Reservation lifecycle: reserve → **commit before any provider call** → settle (success) or
  release (failure). Every exit path after reserve must end in exactly one of the two.
- Unknown provider cost settles the full reserved amount with `measurement="unknown"`: be
  conservative, never zero.
- Idempotency keys are tenant-scoped `(account_id, key)`. Replays compare a payload hash or
  fields and return 409 on mismatch.
- Every query on user data filters `account_id`; notes also filter `owner_user_id`.
- These paths are only really exercised on Postgres: run `python scripts/tasks.py test-integration`
  (needs Docker) or report it as NOT RUN.
- Migrations: add a new revision, never edit an applied one; keep `models.py` in sync; downgrade
  must not silently drop user data.
