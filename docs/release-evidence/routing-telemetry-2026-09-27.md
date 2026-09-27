# Karmi routing/telemetry actor — implementation evidence

Observed 2026-09-27 on Windows x64, Python 3.14.3. Candidate branch `Kashyep/routing-telemetry-loop` from clean baseline `00b7224`. This is implementation evidence, **not** a production-readiness or deployment attestation. Parakh (`rossonerian-parakh`) is a separate repository and was not available for consumer testing.

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
| `python scripts/tasks.py test-unit` | PASS: 211, including migration/model parity, signed-bundle rejection and duplicate-key strict JSON parsing (red before fix, green after), telemetry spool/replay/finalization and routing probabilities. |
| `python scripts/tasks.py test-e2e` | PASS: 37, including static parity, shadow-only selection, tampered bundle fallback, router/feature failure eligibility, known/unknown provider expense, failed-tool expense retained with customer refund/retry, telemetry outage, no-eligible deferral, guardrail rollback, feedback authorization, admin-only observability and export roundtrip. |
| `python scripts/tasks.py benchmark-demo` | PASS: offline 60-case suite validation and 5-attempt fixture demo; results have incomplete coverage and prove no model-quality superiority. |
| `python scripts/tasks.py routing --help`, `python scripts/tasks.py telemetry --help`, `python scripts/generate_routing_contracts.py` | PASS: actual CLI command dispatch and schema generation. No live provider invoked. |
| `docker info --format '{{.ServerVersion}}'` | FAILED to connect to `dockerDesktopLinuxEngine`; `python scripts/tasks.py test-integration` **NOT RUN**. |

Synthetic 4-way concurrent, 100-request local-route test on disposable SQLite (`python scripts/bench_routing_latency.py --requests 100`): baseline p50/p95 16.60/192.71 ms, 56.23 req/s; candidate p50/p95 40.12/383.49 ms, 28.02 req/s. This is an observed regression in this environment, not a production PostgreSQL forecast. A prior 24-request run was noisy. Investigate/measure on disposable PostgreSQL before release; no latency SLO is asserted.

## Compatibility and security/privacy

The `/v1/messages` response shape is unchanged; idempotent replay now preserves the executed route in the existing outbox payload. Default live-disabled static requests keep the baseline local response. Known deviations from the implicit route are documented in ADR-0003: context/cost eligibility and an open provider circuit can choose local where the baseline attempted live. Failed paid attempts with no usage response are marked unknown rather than free. Bundle verification rejects executable/unlisted files, checks signatures, limits, schema and self-test; the policy may only choose already eligible routes. Telemetry pseudonyms are domain-separated HMACs derived from the auth secret; raw request text, context, responses and request fingerprints are not exported. Feedback is scoped to the caller's run; correction text storage is opt-in and sanitized. Export is privacy-validated and checksummed, **not signed**. Spool and export files require filesystem permissions and a retention/backup policy.

## NOT VERIFIED / release blockers

- Real PostgreSQL/Redis integration, concurrent-money and restore/rollback gates: Docker daemon unavailable for this candidate. Migration was checked under SQLite only. No production migration was run.
- Parakh consuming `TelemetryBatchV1`, signing real bundles and historical/replayed off-policy quality: external repository absent. Synthetic contract/self-test is not consumer integration.
- Declared TypeSafe rate card, 128k context assumption, unknown actual usage, provider token/output bounding and 20k-micro two-call worst-case estimate: no authorised live provider test or verified pricing. Production paid routing must remain disabled pending validated bounds and spend authorization.
- Static-route load regression on SQLite as measured above; no PostgreSQL comparative load profile. Live/device/payment/channel/manual gates not run. WhatsApp remains policy-disabled; no paid checkout, customer messaging or deployment.
- Independent verifier and security review **BLOCKED**. Orca attempted both Antigravity Gemini HIGH reviewers and retried the verifier with a 180-second readiness window. `worker-read` showed PowerShell `agy : The term 'agy' is not recognized`; none ran the task. Owned terminals were released. This is not an independent acceptance and cannot be waived by the Boss.

**Status:** implemented and synthetic automated gates passing; production-readiness **NOT VERIFIED**, deployment **NOT DONE**. Rollback: `router_mode=static` (traffic), `python scripts/tasks.py routing rollback --reason INCIDENT_CODE` (persistent store); telemetry tables/migration are additive. No policy activation or destructive retention action performed on production data.
