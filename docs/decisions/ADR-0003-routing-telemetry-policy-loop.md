# ADR-0003 — Versioned routing, production telemetry and the Parakh policy loop

- Status: accepted (implementation in progress on `Kashyep/routing-telemetry-loop`)
- Date: 2026-09-27
- Base commit: `00b7224`
- Scope: Karmi is the production actor. It executes and logs; it never trains. Parakh
  (`rossonerian-parakh`, separate repository, not present on this host) produces candidate
  policy bundles from exported telemetry.

## 1. Baseline (K0 audit, before this change)

| Concern | Where it lived | Notes |
|---|---|---|
| Request entry | `api.send_message` (`POST /v1/messages`, sync handler, threadpool) | idempotency → `policy_for` → `reserve_budget` → commit → context → generate → `_apply_intent` → `persist_completed_run` → `settle_budget` |
| "Routing" | implicit in `services.fake_generate` | `settings.live_models_enabled` ⇒ `typesafe-system-one`, else `fake-economy`; provider failure falls through to heuristics (`fake-economy`) |
| Tier gating of routes | none | `PlanPolicy.allowed_routes` names `fake-balanced`/`fake-advanced`, never executed or enforced; Trika's list omits the route it actually runs |
| Eligibility | none explicit | live gate = settings flag; request cap enforced only by clamping the reservation |
| Provider execution | `providers.classify_intent`, `providers.score_notes_relevance` | only module allowed to import `typesafe_sdk`; returns `ProviderCall` |
| Cost | `providers._cost_micro` (rate card), `services.estimate_request_cost_micro`, `measured_cost_micro`, `settle_budget` → `cost_ledger` | micro-units, unknown ≠ 0 |
| Retry | `typesafe_sdk.RetryPolicy(max_retries=1)`; heuristic fallback on failure | |
| Tools | `api._apply_intent` (Note write for `store_memory`, Task write for `create_task`) | tool actions follow a validated intent label |
| Context/memory | `services.build_note_context` (+ optional live relevance scoring) | |
| Prompts/harness | inline strings in `providers.py` | unversioned |
| Outcome finalised | `persist_completed_run` (+ outbox) | no quality/outcome telemetry |
| Persistence | SQLAlchemy 2 sync ORM; PostgreSQL in production, SQLite dev/test; Alembic | `test_migrations` enforces no drift |
| Telemetry | Python logging only; `/admin/*` redacted views | no request ids, no decision records |

## 2. Decision

Additive layers behind configuration; `DAILY_AGENT_ROUTER_MODE=static` (default) reproduces
the baseline selection exactly.

```
POST /v1/messages
  ├─ features.build_routing_context  (no raw text leaves this step; domain is a keyword class)
  ├─ eligibility.filter_eligible     (tier, disabled, live flag, context, tools, structured
  │                                   output, provider health, request/period cost ceilings)
  ├─ Router: live policy (static | bandit | canary split) + optional shadow policy
  │     learned policy failure → StaticRoutingPolicy, reason recorded
  ├─ execute selected route (services.fake_generate(route=...)), existing budget path intact
  └─ telemetry.emit(RunRecord)  → bounded queue → writer thread → DB   (spool on overflow)
                                   └─ finalizer (attribution window) → exporter → TelemetryBatchV1
PolicyBundleV1 → verifier (signature, checksums, schema, compat, self-test) → PolicyStore
     (install/stage → shadow → promote; atomic state.json swap; rollback = one operation)
```

### Frozen contracts (code is authoritative)

| Contract | Module |
|---|---|
| `RoutingContext`, `ModelCandidate`, `RoutingDecision`, `EligibilityResult`, `RoutingOutcome`, `FEATURE_NAMES_V1` (`routing-features-v1`) | `src/daily_agent/routing/models.py` |
| `RoutingPolicy` protocol + invariants | `src/daily_agent/routing/policy.py` |
| Registry (`fake-economy`, `typesafe-system-one`), `ProviderHealth`, `entitlement_map()` | `src/daily_agent/routing/registry.py` |
| Telemetry records, `TelemetryBatchV1` | `src/daily_agent/telemetry/events.py` |
| `PolicyBundleV1` (all JSON documents), `LoadedBundle` | `src/daily_agent/policy_artifacts/schema.py` |
| LinUCB scoring (shared by self-test and live policy) | `src/daily_agent/policy_artifacts/scoring.py` |
| Harness versions, built-in prompts | `src/daily_agent/harness/versioning.py` |
| Settings `router_*`, `telemetry_*` | `src/daily_agent/config.py` |
| Tables `telemetry_*` | `src/daily_agent/models.py`, migration `5e7a9c1d3f20` |

JSON Schemas for Parakh are generated from these models into `docs/contracts/`.

### Key rules

1. A learned policy chooses only among eligible candidates; eligibility is computed before
   and independently of any policy. Bundle `tier_restrictions` can only narrow.
2. Every decision records `selection_probability` and the full `action_probabilities`.
   Deterministic policies log probability 1.0. Exploration is an explicit ε-mixture whose
   probabilities are exact; disabled by default and allowlisted per tier and domain.
3. Shadow means shadow *selection*: the shadow model is never called.
4. Bundles are data (JSON only), Ed25519-signed over `checksums.json`; every file hashed; any
   unexpected file, symlink, oversize file, schema/feature/model/version mismatch or self-test
   disagreement rejects the bundle. The live policy is untouched until an atomic swap.
5. Telemetry never blocks or fails a request. Mandatory records (run with decisions,
   probabilities, attempts, tool events, outcome; signals; feedback) are spooled to disk
   rather than dropped; optional ops events may be dropped.
6. Telemetry stores categories, numbers, identifiers and keyed pseudonyms. No message text,
   memory content, tokens or contact details. Correction text is opt-in and sanitised; the
   exporter re-scans the whole batch and fails closed.
7. Reward interpretation belongs to Parakh. Karmi stores raw signal type, strength and
   confidence.
8. Pseudonym key = HMAC(`auth_secret`, domain tag): no new production secret; rotating the
   auth secret rotates pseudonyms (documented in the runbook).

## 3. Known deviations from the baseline

- Request-cost eligibility uses the expected cost of the live route (input + context budget
  at the declared rate). An Ananta request near the 20k-character limit with a full context
  budget exceeds the 2,000-micro cap and is served by `fake-economy` instead of attempting the
  live route. Before, the reservation was silently clamped to the cap.
- An open provider circuit skips the live call and serves `fake-economy` directly; before,
  the call was attempted and fell back to the same heuristics.

## 4. Non-goals (first implementation)

Neural routers, online updates, PPO, automatic prompt mutation, Parakh write access,
executable artifacts, raw conversation storage, autonomous promotion.
