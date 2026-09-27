# Karmi routing/telemetry actor — implementation evidence

Observed 2026-09-27 on Windows x64, Python 3.14.3. Candidate branch `Kashyep/routing-telemetry-loop`: implementation commit `08e4c7b` from clean baseline `00b7224`, test-sink fix `0d96aa3`, then a telemetry-writer and security-review remediation commit. Gate counts below are for the final remediated tree. This is implementation evidence, **not** a production-readiness or deployment attestation. Parakh (`rossonerian-parakh`) is a separate repository and was not available for consumer testing.

## Baseline and architecture

The baseline request ran idempotency → budget reservation/commit → note context and optional TypeSafe calls → intent/tool persistence → settlement/outbox. `live_models_enabled` implicitly chose TypeSafe versus local heuristics; there was no explicit eligibility, policy artifact, decision propensity or telemetry export. The new flow builds non-sensitive features, filters eligible routes before selecting static/LinUCB/shadow/canary policy, executes only the live choice, settles costs and asynchronously records its selection probability, attempts, tools and immediate outcome. The outcome finalizer waits for attribution signals; the exporter writes validated, checksummed `TelemetryBatchV1`. Only Parakh trains; Karmi accepts Ed25519-signed JSON `PolicyBundleV1` through verification, explicit promotion and rollback. Default `router_mode=static`, exploration off, live model calls off.

Key files:

| Concern | Files |
|---|---|
| HTTP/auth and money path | `src/daily_agent/api.py`, `services.py`, `providers.py`, `schemas.py`, `wiring.py` |
| Router | `routing/{models,features,eligibility,registry,static_policy,bandit_policy,shadow_policy,runtime,guardrails}.py` |
| Signed artifacts | `policy_artifacts/{schema,scoring,verifier,store,__main__}.py` |
| Telemetry | `telemetry/{events,recorder,pseudonym,sanitizer,collector,writer,finalizer,exporter,retention,__main__}.py` |
| Harness and metrics | `harness/versioning.py`, `observability.py` |
| Data/contract/ops | `models.py`, `migrations/versions/5e7a9c1d3f20_routing_telemetry_tables.py`, `config.py`, `docs/contracts/*.schema.json`, `scripts/generate_routing_contracts.py`, `docs/runbooks/routing-telemetry.md`, `.env.example`, `CLAUDE.md` |
| Acceptance/load | `tests/unit/{routing,telemetry,policy_artifacts}/`, `tests/e2e/test_routing_telemetry.py`, `tests/conftest.py`, `scripts/bench_routing_latency.py` |

## Executed automatic and smoke checks

| Gate / scenario | Observation |
|---|---|
| K0 baseline | lint, secret scan, mypy (18 files), unit 47, e2e 22 passed at `00b7224` before changes (prior-session evidence). |
| `python scripts/tasks.py lint` | PASS: ruff and secret scan. A synthetic private-key fixture initially matched the scanner; split its source literal without weakening scan, then the gate passed. |
| `python scripts/tasks.py typecheck` | PASS: mypy strict, 50 source files. |
| `python scripts/tasks.py test-unit` | PASS: 220, including migration/model parity, signed-bundle rejection, duplicate-key strict JSON, single-read verification under a mid-verify file swap, directory/version binding, rollback quarantine/no-op promote/deactivate-then-rollback, batch dedupe with retry attribution, export stamping and next-batch pickup of rows written mid-export, and retention of late/orphan rows. |
| `python scripts/tasks.py test-e2e` | PASS: 41, including static parity, shadow-only selection, a tampered signed file rejected with `bundle_rejected_checksum_mismatch`, router/feature failure eligibility, known/unknown provider expense, provider-fault DEFERRED refund with expense kept, unverified live spend rejected, a >20k message rejected before budget/provider, retryable no-route 503, feedback dedupe, telemetry outage, guardrail rollback, feedback authorization, admin-only observability and export roundtrip. |
| `python scripts/tasks.py benchmark-demo` | PASS: offline 60-case suite validation and 5-attempt fixture demo; results have incomplete coverage and prove no model-quality superiority. |
| `python scripts/tasks.py routing --help`, `python scripts/tasks.py telemetry --help`, `python scripts/generate_routing_contracts.py` | PASS: actual CLI command dispatch and schema generation. No live provider invoked. |
| `docker info --format '{{.ServerVersion}}'` | First attempt failed to connect; after Docker Desktop started it reported `29.6.1`. `python scripts/tasks.py test-integration` (PostgreSQL/Redis): PASS, 2 passed, on the candidate and again after review remediation. |

Synthetic 4-way concurrent, 100-request local-route test (`python scripts/bench_routing_latency.py --requests 100`), measured after the telemetry-writer rewrite and **before** the review remediation below. The remediation does not change the static-route hot path; the benchmark was not re-run afterwards.

| Store | Baseline p50 / p95 ms, req/s | Candidate p50 / p95 ms, req/s |
|---|---|---|
| SQLite | 17.2 / 289.87, 53.67 | 18.81 / 351.84, 45.89 |
| PostgreSQL (disposable Docker), run 1 | 79.58 / 149.55, 45.7 | 91.32 / 146.31, 41.59 |
| PostgreSQL (disposable Docker), run 2 | 75.17 / 126.55, 49.52 | 90.93 / 139.81, 41.22 |

Observed candidate throughput is ~10–16% lower and p50 ~15–20% higher. Per request, the baseline issues 24 SQL statements and the candidate ~27.5–29.4; the additional ones run on the telemetry writer thread. This is a local synthetic measurement, not a production forecast; no latency SLO is asserted.

## Independent review and remediation

- `AcceptanceVerifier` (verifier agent): **ACCEPT** for the task-card claims; minor deprecation notes only.
- `SecurityReviewer` (security-reviewer agent): **REWORK** with F1–F9. Each fix has a regression test that failed on `0d96aa3` (run in a throwaway worktree) and passes now, except F1's external part.
  - F1 (BLOCKER, live reservation below possible spend): **contained, not resolved**. `providers.LIVE_PROVIDER_SPEND_VERIFIED=False` makes the live route ineligible (`provider_spend_unverified`) in every configuration, and the SDK client refuses to construct. Messages over 20k characters get a 413 before retrieval or a budget hold. Note scoring is limited to the context budget. The single-call estimate and `min(cap, estimate)` clamp remain; see blockers.
  - F2: a provider-fault `DEFERRED` refunds the customer and keeps the provider expense.
  - F3: rollback never reselects the failing or a quarantined version, and quarantine is persisted in `state.json`. Re-promoting the active version is a no-op, deactivate-then-rollback stays static, and guardrail rollback is compare-and-set. A CLI smoke on a temporary store showed each of these.
  - F4: each bundle file is read once (O_NOFOLLOW where available, regular-file and size check); the hashed bytes are the parsed bytes. The signed version must match its directory.
  - F5: feedback id is deterministic per run and type. Repeats return `duplicate` and are not emitted. Collector health reports `spool_bytes`.
  - F6: an exported run is kept while it has unexported children; orphans older than the cutoff are purged; deletes are chunked (including actor purge).
  - F7: every exported child row is stamped; rows written during an export go out in the next batch.
  - F8: no-route returns 503 with `Retry-After` and stores no run under the idempotency key; the same key succeeds once a route is available.
  - F9: the E2E test tampers signed `routing_policy.json` and asserts `bundle_rejected_checksum_mismatch`.
- Re-review (read-only, tests read but not run by the reviewer): F2, F3, F4, F6, F7, F8, F9 RESOLVED; F1 PARTIAL (contained); F5 PARTIAL. The in-flight emit dedupe was added after the re-review. Still open: no per-principal rate limit and no spool size cap. New notes:
  - N1: an older build treats the new `state.json` field as corrupt (fail-closed static; documented in the runbook).
  - N2: unchunked actor purge; fixed.

## Compatibility and security/privacy

The `/v1/messages` success shape is unchanged. Contract changes: a no-route deferral is now HTTP 503 `NO_ELIGIBLE_ROUTE` with `Retry-After` (previously 200 DEFERRED persisted under the key), messages over 20,000 characters are 413 before any budget hold, and feedback responses add `duplicate`; idempotent replay now preserves the executed route in the existing outbox payload. Default live-disabled static requests keep the baseline local response. Known deviations from the implicit route are documented in ADR-0003: context/cost eligibility and an open provider circuit can choose local where the baseline attempted live. Failed paid attempts with no usage response are marked unknown rather than free. Bundle verification rejects executable/unlisted files, checks signatures, limits, schema and self-test; the policy may only choose already eligible routes. Telemetry pseudonyms are domain-separated HMACs derived from the auth secret; raw request text, context, responses and request fingerprints are not exported. Feedback is scoped to the caller's run; correction text storage is opt-in and sanitized. Export is privacy-validated and checksummed, **not signed**. Spool and export files require filesystem permissions and a retention/backup policy.

## NOT VERIFIED / release blockers

- Real PostgreSQL/Redis integration: 2 integration tests pass locally in Docker. Concurrent-money, restore/rollback gates and production migration were not run.
- Parakh consuming `TelemetryBatchV1`, signing real bundles and historical/replayed off-policy quality: external repository absent. Synthetic contract/self-test is not consumer integration.
- **F1 financial gate (blocking live paid routing):** there is no verified TypeSafe billable input/output/retry rate card and no SDK max-output/max-spend parameter. So no proven worst-case bound exists for score + classify with retries, and the reservation still clamps to the request cap. Live spend is hard-disabled in code. Enabling it needs verified rates, bounded output and retries, a reservation ≥ the worst case (with a test), and spend authorisation.
- Feedback endpoint has no per-principal rate limit. The telemetry spool has no size cap by design (mandatory records); `spool_bytes` must be alerted on.
- Live/device/payment/channel/manual gates not run. WhatsApp remains policy-disabled; no paid checkout, customer messaging or deployment.
- Orca Antigravity Gemini workers could not launch (`agy` not installed in this Windows terminal). The verifier and security reviews above were run as task-tool subagents, not Orca workers; which model served them was not independently confirmed.

**Status:** implemented and synthetic automated gates passing; production-readiness **NOT VERIFIED**, deployment **NOT DONE**. Rollback: `router_mode=static` (traffic), `python scripts/tasks.py routing rollback --reason INCIDENT_CODE` (persistent store); telemetry tables/migration are additive. No policy activation or destructive retention action performed on production data.
