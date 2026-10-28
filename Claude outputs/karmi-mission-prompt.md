# MISSION: Karmi MVP + first tester release (gateway, free-model scoring, rules router)

## GOAL
Take Karmi (`/home/rosso/Projects/Karmi`) and Parakh (`/home/rosso/Projects/Parakh`) from the current state to a verified MVP and a release-ready first GitHub Release for testers: a model gateway with a rules-based router over free OpenRouter models, per-tier quotas, a student-focused feedback loop, and an Android build with a hosted test backend. Run end to end in one uninterrupted pass. No checkpoint questions. Stop only at the owner gates listed below.

## CONTEXT
Product: a cheap AI platform for Indian students (chat now, agentic tasks later, phone and desktop). Cheap/free models on low tiers, good-but-cheap models on higher tiers, one price for everyone, no student verification, no discounts. A router chooses the model per request. Karmi is the product. Parakh is the offline lab that scores, trains and verifies; it never runs in the live request path.

Facts read from docs and code (NOT verified by running anything; re-verify in WP0):
- Karmi: FastAPI package `daily_agent`, SQLAlchemy + Alembic, Flutter app in `mobile/`, Clerk auth, Postgres target, SQLite dev, Redis. Tiers ananta/yanta/trika/parth (contract spells `part`, mapped by CONTRACT_TIERS). Money is BigInteger micro-units. Request flow: idempotency, reserve_budget, commit, build_note_context + `fake_generate`, `_apply_intent`, persist, record_routing_evidence, settle_budget; on failure release_budget.
- `fake_generate` in `services.py` is a hard-coded if/else chain. `plans.py` uses fake route names (`fake-economy`, `fake-balanced`, `fake-advanced`). `providers.py` is documented as the only place allowed to call a live model. `opencode.py` has an 11-model free allowlist and one global model id.
- `parakh/routing.py`: `KNOWN_ACTIONS` and `model_registry()` may omit `OPENCODE_ACTION` (unverified, possible bug).
- Karmi has about 1,150 uncommitted changed lines on branch `readiness-harness` (29 modified files plus untracked). Do not lose them.
- Parakh: `model_lab` offline CLI. Frozen 60-case seed bank (36 train, 12 calibration, 12 sealed holdout, holdout consumed once). Live runs need a frozen hash-verified plan and `--allow-paid`. Contracts: TelemetryBatchV1 (Karmi to Parakh), PolicyBundleV1 (Parakh to Karmi, Ed25519 signed). Karmi loads bundles in SHADOW only.
- Parakh `providers/live.py` was not read; whether it supports OpenRouter is unknown.
- Last Parakh readiness run (Sep 28): PRODUCTION READY: NO.

Decisions already made by the owner (do not revisit):
1. Score all free OpenRouter models available at run time.
2. Use Revenue_model figures for plans (Ananta Rs 0, Yanta Rs 149, Trika Rs 399, Part Rs 899, "Deep Task" billing unit).
3. Build a student-focused synthetic prompt set (code, maths, study explanations, Hindi and mixed Hindi-English).
4. Free models only for now. With zero-price models, rupee budgets cannot limit usage, so limits are per-tier request/token quotas plus provider rate limits and cooldowns.
5. One price for everyone; no verification or special discount.
6. iOS is out of scope.

Reference: the written work order is the Docs artifact "Karmi MVP and Tester Release: Work Order" (claude.ai/artifact/61zNCcDoSvqx7LzF2FKvWg). If you can read it, use it for detail. If it disagrees with the code or git history, the code and git win; note the disagreement.

## CONSTRAINTS
Rules, highest priority first:
1. Correctness, then verification, then minimal scoped changes, then clarity.
2. Git: inspect status/log/remote before any git action. Work on a new branch from the current state. Commit intentionally in small commits. NEVER reset --hard, force-push, rewrite history, discard uncommitted work or delete a branch. Do NOT push, open a PR, tag or publish a release without explicit owner approval. Save a durable patch of the current Karmi working tree outside the repo before anything else.
3. Secrets: never open, print or commit `.env.clerk`, `.env.neon` or any key. The OpenRouter key arrives in an ignored local file (`.env.openrouter`); read it only through the config loader; never log it.
4. Cost: free models only. If any model reports a non-zero price, exclude it and stop that call path. No paid provider calls. No call beyond the owner-approved request cap.
5. Privacy: only models whose data terms are known and acceptable may receive private note content. Unknown means not allowed.
6. Protected files: do not edit frozen benchmark banks, `benchmarks/**`, signed bundles, or existing contract schemas except by additive, versioned change with tests.
7. No new dependency unless genuinely needed. Match existing conventions. No drive-by refactors; flag adjacent issues instead.
8. No hidden retries, no silent fallbacks, no unbounded loops. If a gate fails after one bounded fix, stop and report.
9. Parallelism: only the "safe parallel" packages below, each agent owning exclusive paths, followed by a review-and-repair pass. Use the cheapest suitable model first; escalate only when it fails.
10. Never claim success without evidence: run the command, report the real output and exit status. Say plainly what you could not verify.

## WORK PACKAGES (order: WP0 alone, then WP1 || WP2 || WP4-UI, then WP3, then WP5, then WP6)

**WP0 Baseline audit and repair** (both repos, no feature work)
- Inspect git state; save the patch; build working environments (Karmi Python 3.12+, Parakh 3.11+, Flutter 3.47.5); do not trust existing `.venv`.
- Run every gate and record output. Karmi: `python scripts/tasks.py lint`, `typecheck`, `test-unit`, `test-e2e`. Parakh: `.venv/bin/python -m pytest -q`. Flutter: `flutter analyze`, `flutter test`.
- Review the 1,150-line uncommitted diff file by file. Add missing OpenCode tests (generated reply, provider failure gives DEFERRED, unknown-cost settlement, candidate privacy, no retries). Check and fix the OPENCODE action registration in `KNOWN_ACTIONS` and `model_registry()`.
- Gate: baseline report; gates pass or every failure is listed with its cause.

**WP1 Score every free model** (Parakh; owns `model_lab/providers/`, a new student-set directory, `docs/live_pilots/`)
- Read `providers/live.py`, `docs/live_pilots/README.md`, `Model_Testing_Spec.md`. Add an OpenRouter adapter (OpenAI-compatible API; confirm base URL, model list and rate-limit behaviour from OpenRouter's current official docs). Key from ignored file; no redirects; timeouts; back off and resume on rate-limit responses; record model id, tokens, latency, finish reason and returned price; abort on non-zero price.
- Add a catalog snapshot command saving a dated JSON of models with zero prompt and completion price plus stated data-use terms.
- Author at least 40 synthetic student cases in a NEW directory (code, maths, study explanations, Hindi and mixed, one long-context summary), with automated checks where possible, plus a sealed holdout.
- Run through the normal path: operator-input YAML, immutable plan, `pilot run`. Propose a request cap after reading the key's rate limits and wait for the owner's approval (owner gate). Score train and calibration cases, 3 repeats, holdout only for the shortlist. Report skipped cases.
- Output: report bundle, provisional shortlist per class, seed registry file (model id, class, price, context, scores, data-terms flag, snapshot date). All scores labelled provisional.
- Gate: `.venv/bin/python -m pytest -q` and `make test-release` pass; no dispatch beyond the cap. Until the cap and key exist, finish everything else and test on the fake provider.

**WP2 Gateway, tiers, rules router** (Karmi; owns new gateway code, generation section of `services.py`, `plans.py`, `config.py`)
- Provider interface returning `ProviderCall`; OpenRouter adapter; fold OpenCode in; reviewed JSON model registry loaded from the WP1 file. Update the CLAUDE.md rule about where live calls may live in the same change.
- Replace fake route names in `plans.py` with allowed model classes per tier; keep plan ids.
- Per-tier daily request and token quotas, per-model cooldown on rate limits. Keep reserve/settle/release with INR micro-unit labels so paid models can be added later.
- Router stage 1: inputs are tier, task type, prompt length, notes attached, structured output needed. Cheapest eligible model that fits; escalate one class on failed validation or regenerate; fallback chain; per-provider circuit breaker; timeouts; at most one retry on a different model; final failure returns DEFERRED and releases the reservation. Add a kill switch setting.
- Replace the `fake_generate` chain with classify, route, generate. Saving a note or creating a task stays a real write. Keep a deterministic demo path when live models are off so tests need no network.
- Tests: router/tier/registry units; e2e with a fake HTTP transport; a test that a model lacking the right data terms never receives private notes; a budget race test in the Postgres integration suite.
- Gate: `lint`, `typecheck`, `test-unit`, `test-e2e`, then `test-integration` with Docker.

**WP3 Feedback and telemetry** (after WP2 interfaces; owns `api.py` feedback routes, `models.py` plus one Alembic migration, `parakh/`)
- Account-scoped feedback table (message, rating, reason) with one migration and an idempotent route. Regenerate creates a new message linked to the previous one with a reason.
- Add sanitized feedback to the TelemetryBatchV1 export if the schema allows it (check `telemetry_batch_v1.schema.json`); otherwise add an additive versioned change with tests. Register every new action in `KNOWN_ACTIONS` and `model_registry()`.
- Gate: a Karmi export imports into Parakh with zero quarantined runs (use the existing cross-repo test as a template).

**WP4 Mobile** (owns `mobile/`; UI can start in parallel with WP2)
- Verify Clerk email-code sign-in on a physical Android phone (owner gate: phone and Clerk setting) and record observations; widget tests do not count.
- Thumbs up/down and regenerate on each reply; first-launch tester notice the user must acknowledge; API client for the new routes.
- Regenerate goldens in the Linux container previously used; `flutter analyze` and `flutter test`.
- Release APK with recorded checksum; signing key is an owner decision.

**WP5 Hardening and hosted test backend** (owns `scripts/`, `Dockerfile`, `ops/`, `config.py`)
- Postgres + Redis integration suite under Docker. Make the production-config audit (`scripts/readiness_config.py`) pass without weakening it. Per-user rate limiting, health endpoint, log redaction, TLS, backup/restore notes, migration rollback rehearsal.
- Propose hosting options with costs. Deploy only after the owner chooses and approves (owner gate).

**WP6 Release preparation**
- Tester guide, tester notice text, known issues, evidence file under `docs/release-evidence/`. Flag the notice for legal review (many students are under 18; India's data protection law applies).
- Prepare commit list, exact diff, APK and checksum. Do NOT push, tag or publish. Present everything and wait for approval.

## OWNER GATES (stop at these, list exactly what is missing, continue with all other work)
OpenRouter key in `.env.openrouter`; approval of the request cap; Docker running; Android phone plus Clerk email-code enabled; hosting choice and approval; signing key decision; tester list; final approval to push, tag and publish.

## STOP AND REPORT (do not route around) when
A gate fails after one bounded fix; a step needs a secret, paid call, push, deployment or Neon migration; a doc and the code disagree; a "free" model shows a non-zero price or rate limits halt the run; a change would touch a protected file.

## DONE WHEN
1. WP0 baseline report exists with real command output; all baseline gates pass or each failure is explained.
2. Parakh has a dated free-model catalog snapshot, the student set (40+ cases), scored reports, a provisional per-class shortlist and a registry file; no calls beyond the approved cap; Parakh tests pass.
3. Karmi routes live requests through the gateway: per-tier model classes, rules router with escalation, fallback and circuit breaker, per-tier quotas, kill switch, privacy eligibility enforced; `lint`, `typecheck`, `test-unit`, `test-e2e`, `test-integration` pass.
4. Feedback is stored, exported and imported into Parakh with zero quarantined runs.
5. Android release APK builds with checksum; Flutter analyze/tests pass; device sign-in run recorded.
6. Production-config audit passes; hosted test backend deployed only if the owner approved.
7. Release evidence file, tester guide and notice are ready; a draft PR is prepared locally; nothing is pushed, tagged or published without approval.
8. Final report lists, per work package: files and commit hashes; commands run with exit status; VERIFIED vs NOT VERIFIED; deviations; blockers; remaining owner inputs. Update Karmi's `Memory.md` with verified state only.
