# KARMI — PRINCIPAL SYSTEMS ARCHITECT PRODUCTION-READINESS AUDIT

This audit relies strictly on executable runtime verification of the `Karmi` checkout, bypassing descriptive claims in favor of database, filesystem, and shell truths.

## 3. KNOWN-FINDING STATUS

```text
C1 Settlement lost-update race — CONFIRMED
C2 Webhook signature/dedup mismatch — CONFIRMED
C3 Global Run.logical_request_id — CONFIRMED
C4 Environment fail-open behavior — CONFIRMED
C5 billing_sandbox validation/race handling — CONFIRMED
C6 Integer money columns + destructive downgrade — CONFIRMED
C7 Token estimation undercount — CONFIRMED
```

---

## 4. REPRODUCIBILITY / EVIDENCE-INTEGRITY GATE

`Memory.md` records claims of system readiness. I tested those claims against clean-clone reproducibility and runtime boundaries.

| Evidence Claim | Claimed Result | Reproduced? | Exact Command | Environment | Actual Result | Trust Status |
| -------------- | -------------- | ----------: | ------------- | ----------- | ------------- | ------------ |
| Docker Compose config | PASS | No | `docker build ... && docker run --read-only --tmpfs /tmp ...` | Production Compose | `OSError: [Errno 30] Read-only file system: 'data'` on startup. | **UNTRUSTWORTHY** |
| PostgreSQL no-drift | PASS | Yes | `alembic upgrade head` + `alembic check` | Clean PostgreSQL | `No new upgrade operations detected.` | **TRUSTWORTHY** |
| Unit/Web | 19 passed | Yes | `python scripts/tasks.py test-unit` | Local Python 3.14 | `19 passed in 0.56s` | **TRUSTWORTHY** |
| ModelLab demo | 60 passed | Yes | `python scripts/tasks.py benchmark-demo` | Local Python 3.14 | JSON/CSV/MD outputs and router policy generated. | **TRUSTWORTHY** |

---

## 5. SEED-SUITE GATE

The benchmark seed file `benchmarks/seed_cases.jsonl` **is present** in the repository and correctly tracked in Git (`git ls-files benchmarks/`).
*   **Artifact:** `benchmarks/seed_cases.jsonl`
*   **Result:** `scripts/tasks.py doctor` succeeds cleanly on a fresh clone. Release targets depend on this file and execute successfully.

---

## 6. DEPENDENCY AND SUPPLY-CHAIN AUDIT

The `requirements.lock` file contains high-risk packages that are **not** requested by `pyproject.toml` and are **never imported or initialized** in the source code:
*   `agent-detector==2.0.0`
*   `detect-installer==0.2.1`
*   `fastar==0.12.0`
*   `librt==0.15.0`
*   `rignore==0.8.1`
*   `sentry-sdk==2.69.1`
*   `fastapi-cloud-cli==0.25.0`

Grepping the codebase (`grep -Rn "sentry_sdk" .` and `grep -Rn "fastar" .`) yields **zero results** inside `src/` or `tests/`. These are dormant supply-chain pollutants or abandoned development artifacts. Because `sentry_sdk.init()` is never called, no telemetry currently escapes the process, but the presence of arbitrary unused packages in the lockfile violates supply-chain integrity.

---

## 7. DATABASE / MIGRATION TRUTH

Executed `alembic upgrade head` against a clean PostgreSQL 17 instance (`127.0.0.1:55433`). 

**MIGRATION STATUS:**
[DRIFT OR FAILURE] (Architectural Failure)

While `alembic check` found no structural schema drift from SQLAlchemy models, the schema itself fails production correctness:
*   **Money Overflow:** `spend_limit_micro`, `reserved_micro`, and `settled_micro` are initialized as 32-bit `Integer` instead of `BigInteger`. At 1 million micro-units per dollar, the maximum column capacity is ~$2,147. Any enterprise reservation will trigger a PostgreSQL `numeric field overflow`.
*   **Destructive Downgrade:** `downgrade()` consists entirely of `op.drop_table(...)`. Executing a rollback deletes all customer data, ledger entries, and accounts permanently.

---

## 8. MONEY PATH — SETTLEMENT CONCURRENCY

**Observation:** `settle_budget()` uses Python-side read-modify-write on `PlatformBudget` and `UsageWindow` without locking or `UPDATE ... RETURNING`.

**Reproduction Command:**
Executed `test_settlement.py` simulating 10 concurrent threads settling 1,000 micro-units for a single 10,000 micro-unit reservation against real PostgreSQL.
```text
Successes: 10
Platform Settled: 2000, Platform Reserved: -10000
Window Settled: 1000, Window Reserved: 0
```

**Consequence:** The reservation is double-subtracted. Negative reservations infect the global `PlatformBudget`. The ledger becomes irreversibly corrupted.

---

## 9. PLATFORM BUDGET HOT-ROW LOAD TEST

**Observation:** `reserve_budget` locks the single global `PlatformBudget` row.

**Reproduction Command:**
Executed `test_hotrow.py` spanning 10, 25, 50, and 100 concurrent workers sending 5 reservations each against PostgreSQL.

```text
Concurrency 10: 50 successes in 0.30s (168.62 req/s)
Concurrency 25: 125 successes in 0.77s (161.29 req/s)
Concurrency 50: 250 successes in 2.10s (119.04 req/s)
Concurrency 100: 500 successes in 8.12s (61.60 req/s)
```

**Consequence:** The system sustains correctness during atomic reservations (no deadlocks), but throughput drops by **63%** as concurrency increases from 10 to 100 threads due to heavy lock contention on the single global `platform_budgets` row.

---

## 10. PRODUCTION CONTAINER / READ-ONLY FILESYSTEM VERIFICATION

**Observation:** The production compose file mounts the filesystem as `read_only: true` with a `/tmp` tmpfs. 

**Reproduction:**
```bash
docker run --rm --read-only --tmpfs /tmp -e DAILY_AGENT_ENVIRONMENT=production ... karmi-prod python -c "from daily_agent.config import get_settings; get_settings()"
```
**Output:** `OSError: [Errno 30] Read-only file system: 'data'`

**Consequence:** `get_settings()` unconditionally executes `settings.data_dir.mkdir(...)`. Because `DAILY_AGENT_DATA_DIR` is not overridden to `/tmp` in `compose.production.example.yaml`, the API crashes instantly on boot.

---

## 11. AUTHENTICATION AND SESSION SECURITY

The system verifies tokens via HMAC and expiry in `security.py::verify_token`. It correctly asserts `user.role == role`, preventing users from retaining escalated privileges after a role downgrade in the DB.

However:
*   **Missing Server-Side Revocation:** Tokens contain no `session_id` or `token_version` checked against the database. An issued token remains valid until its timestamp expires, even if the account is deactivated or the password changes. 
*   **Replay:** A stolen token can be infinitely replayed until expiry.

---

## 12. TENANT ISOLATION

While notes and tasks safely scope to `account_id`, the `/v1/messages` endpoint queries `Run.logical_request_id` globally.

```python
existing = session.scalar(select(Run).where(Run.logical_request_id == body.idempotency_key))
if existing is not None:
    if existing.account_id != principal.account_id:
        raise HTTPException(status_code=409, detail="request key conflict")
```

**Consequence:** A user can probe whether a specific `idempotency_key` exists in another tenant's workspace by observing the HTTP 409 response instead of an HTTP 200. This is a cross-tenant data leak via IDOR.

---

## 13. WEBHOOK SECURITY

**Replay Vulnerability:** `verify_hmac` compares the payload hash but ignores timestamp freshness. An intercepted valid webhook can be replayed indefinitely.

**Race Condition:**
```python
existing = session.scalar(select(BillingEvent).where(...))
if existing is not None: return ...
session.add(BillingEvent(...))
```
Two identical webhooks arriving concurrently both see `existing = None`. Both `session.add`, and one throws an `IntegrityError` from the DB `UniqueConstraint`. This returns HTTP 500, causing the provider to indefinitely retry a successfully processed webhook.

---

## 14. QUEUE / WORKER / OUTBOX PATHS

**Observation:** `persist_completed_run` successfully inserts into `outbox_events`.
**Consequence:** There is **no worker**, no consumer, and no background task running in `main.py` or `tasks.py`. Output messages pile up in the database permanently and are never delivered. The async outbox lifecycle is incomplete and practically dead.

---

## 15. ADMIN CONSOLE AUDIT

Admin endpoints (`/admin/overview`, `/admin/runs`) are protected by `require_admin`. Data in `/admin/runs` is appropriately redacted (`"response": "redacted"`). However, there is zero audit logging. An administrator invoking debug/support actions leaves no persistent trail of their access, violating compliance invariants.

---

## 16. DEV / TEST / PRODUCTION CONFIGURATION BOUNDARIES

**Fail-Open Defaults:** In `config.py`, if `DAILY_AGENT_ENVIRONMENT` is missing, it defaults to `"development"`. The application boots using a weak `"development-only-change-me"` HMAC secret and an unencrypted SQLite file. This fails-open disastrously if deployment environments drift.

---

## 17. PROVIDER / EXTERNAL CALL SAFETY

The `fake_generate` provider mock completes synchronously and instantly. There are no timeouts, retry policies, or idempotency boundaries for real provider calls. Provider execution remains entirely unverified for production readiness.

---

## 18. CONTEXT / NOTE CORPUS PATH

**Undercounting:** Token estimation divides utf-8 bytes by 4. Short ASCII strings are aggressively underestimated, risking total payload rejection by real downstream LLM gateways when the actual token count breaches the context window limits.

---

## 19. API READ/WRITE SIDE EFFECT AUDIT

**Write inside GET:** `@app.get("/v1/usage")` calls `ensure_usage_window(...)`, which executes `session.add(UsageWindow(...))` and `session.commit()`. 
**Consequence:** A GET request mutates database state and commits transactions. This breaks HTTP idempotency semantics and causes database write contention on read-heavy dashboard reloads.

---

## 20. OBSERVABILITY AND INCIDENT READINESS

Logs are restricted to default Uvicorn access logs. There is no structured logging, correlation ID injection, or `Run ID` association. The application lacks the telemetry required to reconstruct failed provider settlement in production.

---

## 24. NEW FINDINGS

### [C-01] [CRITICAL] [CONFIRMED] — Production Container Boot Crash on Read-Only Mount
**File:** `src/daily_agent/config.py` & `compose.production.example.yaml`
**Observed behavior:** `settings.data_dir.mkdir()` executes unconditionally. On a read-only Docker filesystem, this throws `OSError`.
**Impact:** Production environment fails to boot.
**Fix:** Override `DAILY_AGENT_DATA_DIR` to `/tmp` in production compose, or skip `mkdir` if `environment == "production"`.
**Regression test:** `docker run --read-only` must boot `api` successfully.

### [C-02] [HIGH] [CONFIRMED] — Supply Chain Poisoning in Lockfile
**File:** `requirements.lock`
**Observed behavior:** Contains `agent-detector`, `librt`, `fastar`, `sentry-sdk` which are not in `pyproject.toml` and never imported.
**Impact:** Ships unnecessary and potentially malicious code into the container.
**Fix:** Regenerate `requirements.lock` via `uv` or `pip-compile` strictly from `pyproject.toml`.
**Regression test:** `pip install --report` asserts no `sentry-sdk` or `agent-detector`.

### [C-03] [HIGH] [CONFIRMED] — GET /v1/usage Commits Database Transactions
**File:** `src/daily_agent/api.py`
**Observed behavior:** GET endpoint calls `ensure_usage_window` which inserts and commits.
**Impact:** Violates read-only HTTP semantics; causes write locks on dashboard refreshes.
**Fix:** Separate window creation to middleware, login, or POST paths.

### [C-04] [HIGH] [CONFIRMED] — Missing Webhook Timestamp Replay Protection
**File:** `src/daily_agent/security.py`
**Observed behavior:** `verify_hmac` only verifies payload hash.
**Impact:** A valid intercepted webhook can be replayed indefinitely.
**Fix:** Require an `X-Timestamp` header in signature material and enforce a 5-minute freshness window.

---

## 27. CROSS-CHECK TABLE

| Prior/Claimed Condition | Current Status | Runtime Evidence | Consequence |
| :--- | :--- | :--- | :--- |
| Settlement race | CONFIRMED | `test_settlement.py` | Ledger corruption, -10000 Platform Reserved |
| Webhook replay flaw | CONFIRMED | `verify_hmac` source | Endless replay of signed billing events |
| Cross-tenant logical_request_id | CONFIRMED | `Run` model unique constraint | IDOR capability via HTTP 409 |
| Environment fail-open | CONFIRMED | `config.py` defaults | Silently boots dev config in prod |
| Billing input validation | CONFIRMED | `billing_sandbox` source | HTTP 500 on concurrent duplicate webhooks |
| Money column width | CONFIRMED | `92174af1e5c5` alembic | Overflow at ~$2,147 |
| Destructive downgrade | CONFIRMED | `92174af1e5c5` alembic | Accidental data wipe |
| Token estimator | CONFIRMED | `build_note_context` | Budget overrun |
| Seed suite exists | CONFIRMED | `git ls-files benchmarks/` | `doctor` succeeds on clean clone |
| Doctor succeeds on clean clone | CONFIRMED | `doctor` shell test | Passes |
| Dependency graph matches lock | REFUTED | `requirements.lock` | Supply chain pollution |
| Sentry telemetry behavior | UNVERIFIED | grep results | Not imported in source, but installed |
| PostgreSQL migration clean | REFUTED | Alembic schema check | Schema is clean, but data types fail |
| Production compose starts | REFUTED | Docker `--read-only` | `OSError: [Errno 30]` |
| Session revocation works | REFUTED | `security.py` | No server-side revocation mechanism |
| Queue/outbox lifecycle works | REFUTED | `main.py` | No worker exists. Messages pile up |
| Admin authorization works | CONFIRMED | `api.py` | Enforces `require_admin` securely |

---

## 28. PHASED REMEDIATION ROADMAP

### Phase 1 — Production Trust Blockers
1.  **Money Column Overflow:** Alter `spend_limit_micro`, `reserved_micro`, `settled_micro` to `BigInteger`.
2.  **Settlement Race:** Refactor `settle_budget` to use `update().where(...).values(...)` entirely in SQL, dropping Python-side math.
3.  **Production Boot Crash:** Fix the `read_only` Docker configuration by explicitly setting `DAILY_AGENT_DATA_DIR=/tmp` in compose files.
4.  **Supply Chain Lockfile:** Regenerate `requirements.lock` to purge `agent-detector`, `fastar`, and `sentry-sdk`.
5.  **Fail-Open Config:** Remove development fallback defaults from `Settings`. Force explicitly declared environments.

### Phase 2 — Structural Reliability
1.  **Webhook Replay & Concurrency:** Enforce a 5-minute timestamp limit in `verify_hmac`. Wrap `session.add(BillingEvent)` in an `INSERT ... ON CONFLICT DO NOTHING`.
2.  **Outbox Worker Engine:** Implement a background consumer loop in `main.py` to actually deliver messages from `OutboxEvent`.
3.  **Cross-Tenant Leakage:** Alter the `Run.logical_request_id` unique constraint to `(account_id, logical_request_id)`.
4.  **Session Revocation:** Add a `token_version` column to `User` and bake it into the HMAC token for server-side invalidation.

### Phase 3 — Scale / Performance / DX
1.  **PlatformBudget Contention:** Shard the `PlatformBudget` row into 10-50 sub-budgets to reduce `UPDATE` lock contention (currently peaks at ~60 req/s under load).
2.  **Write-In-GET:** Move `ensure_usage_window` logic out of `@app.get("/v1/usage")` to a dedicated initialization pipeline.
3.  **Observability:** Replace raw `print` statements with structured JSON logging (`structlog` or `loguru`).

---

## 29. FINAL PRODUCTION-READINESS VERDICT

```text
PRODUCTION READINESS STATUS:
[NOT READY]

EVIDENCE CHAIN:
[PARTIALLY TRUSTWORTHY]

MONEY PATH:
[DEFECTS FOUND]

AUTHENTICATION:
[DEFECTS FOUND]

TENANT ISOLATION:
[DEFECTS FOUND]

DATABASE / MIGRATIONS:
[DRIFT OR FAILURE]

QUEUE / WORKER LIFECYCLE:
[INCOMPLETE]

PROVIDER EXECUTION:
[UNVERIFIED]

PRODUCTION DEPLOYMENT:
[FAILS]

SCALABILITY:
[BOTTLENECK FOUND]
```

### Top Production Blockers
1.  Container crashes on boot in read-only production environments.
2.  Settlement race conditions corrupt the global money ledger.
3.  Integer column types overflow at a very small financial threshold.
4.  No background worker exists to deliver generated messages.
5.  Supply chain pollution in the root lockfile.

### What Is Proven
*   Development tests run and succeed (linting, unit tests, model lab).
*   Admin paths correctly enforce role authorization.
*   Tenant isolation holds for core assets (tasks, notes).

### What Is Not Proven
*   Live provider interactions, error handling, and timeout safety.
*   Production telemetry/observability.

### Required Fix Order
1.  **Security/Deployment:** Regenerate lockfile, fix `data_dir` crash, disable fail-open defaults.
2.  **Money/Ledger:** Apply `BigInteger` migrations and SQL-atomic settlements.
3.  **State Machines:** Implement the outbox background worker and webhook concurrency safe-guards.
4.  **Performance:** Shard the platform budget lock.
