# Daily Agent implementation memory

## MVP + tester-release branch `mvp-gateway` (2026-10-19) — verified state only

- Branch `mvp-gateway` (from `readiness-harness` working tree; pre-work patch saved to
  `~/karmi-backups/`). Nothing pushed, tagged or published.
- Implemented and verified (commands in `docs/release-evidence/mvp-tester-release-2026-10-19.md`):
  gateway (`src/daily_agent/gateway/`: registry, OpenRouter + OpenCode adapters, rules router,
  breaker/cooldown, kill switch), tier model classes + daily request/token quotas, feedback +
  regenerate routes, sanitized feedback in TelemetryBatchV1, per-user rate limit, log redaction,
  Flutter feedback UI + tester notice.
- NOT done / blocked on owner: OpenRouter key and request cap (no live scoring, registry is a
  seed), Docker (integration ran on local PostgreSQL 18 + Valkey instead), Android phone + Clerk
  email-code check, hosting + signing choices, tester list, legal review, push/tag/publish.
- 2026-10-19 update: key supplied (free tier, 50 req/day) -> capped probe only (7 models answered), live gateway
  smoke OK, access codes + server-address UI + podman integration runner added, `v0.1.0-beta.1` prepared. Still
  NOT verified: device sign-in (phone dropped off adb), hosted backend (none deployed), full pilot.
- Parakh branch `openrouter-student-set` holds the OpenRouter adapter, catalog snapshot, registry
  builder and the 49-case student set; its `pilot run` cannot yet run that set (see known-issues).
- 2026-10-21: merged origin/main history; PR #22 telemetry stack (harness/, policy_artifacts/, routing/, telemetry/, wiring.py, observability.py, migration 5e7a9c1d3f20) superseded by parakh/ + gateway and removed from the tree.


## Current Karmi readiness work (2026-10-10)

- Working checkout: `/home/rosso/Projects/Karmi`, branch `readiness-harness`, baseline `0c3d11e`;
  all existing local setup and implementation changes are preserved and remain uncommitted.
- Clerk login presentation is now Karmi-owned: email-code sign-in/sign-up form using Clerk for
  verification/session only. Dashboard must enable email-code sign-in/verification. Current SDK
  remains `clerk_flutter 0.0.18-beta`. No real phone sign-in/API-to-Neon check has been performed.
- OpenCode readiness audit: no dynamic best-model selection exists. Chat calls `fake_generate` and
  echoes draft text; optional TypeSafe calls classify/score context only. Parakh routes static and
  records shadow decisions; it refuses canary/production transitions. ModelLab seed suite (60
  cases) validates; it has no live runner and does not support evidence-backed model comparisons.
- Review: `docs/reviews/OPENCODE-AI-001.md`. Current OpenCode Zen docs show free models are
  temporary; some free endpoints allow prompt use for model improvement or prohibit confidential
  data. No key was read and no model API request was made.
- Updated README and Clerk runbook to describe the present UI and AI readiness accurately.
- Verification: Flutter analyzer PASS, Flutter screen tests PASS (29), seed validation PASS (60),
  Parakh + ModelLab targeted Python tests PASS (24). Production readiness is still BLOCKED; see
  `scripts/readiness_config.py`, Phase gates, and review.
- Next: implement a privacy-filtered OpenCode adapter and candidate-only live evaluation runner only
  after the operator privately configures a key, selects acceptable free-model data terms, and
  explicitly approves a bounded test. Then run the model experiment, implement the evidenced route,
  execute release gates, and request final approval before any GitHub publication.

- Updated UTC: 2026-09-10T14:50:54Z
- Branch: `main`
- Baseline commit: `b67c964288e24bf5d3494368766b9c5a7ed25e7f`
- Current phase: Phase 0 complete; local foundations for Phases 1–3 and 6 implemented
- Canonical source: `docs/blueprint/`

## Verified baseline

- New repository; no pre-existing implementation or user code was present.
- Host is Windows with Python 3.14.3, Node 26.1.0, Docker 29.6.1 and Codex CLI 0.153.4.
- No Ubuntu WSL distribution is available; this run uses one native-Windows checkout/toolchain.
- Native child tasks accepted requested model/effort parameters; effective model metadata was not exposed.
- Official WhatsApp Business Solution Terms were rechecked 2026-09-10 and remain last modified
  2026-03-06. General-purpose AI as primary functionality is restricted outside the stated
  EEA/Brazil number exception. India-first WhatsApp stays disabled.

## Decisions

- Promote the owned web/PWA surface to the initial customer channel for the local release
  candidate. Preserve a disabled official WhatsApp adapter boundary for later eligibility review.
- Use a modular FastAPI/PostgreSQL design and an offline SQLite ModelLab. Development policies
  are unmistakably synthetic; paid checkout and live model/provider calls default off.

## Accepted implementation

- Worker commits accepted for integration: WEB-001 `4488110`; LAB-001 `53e72d4`; LAB-002 `0ad6849`.
- Backend: signed local sessions, tenant-scoped notes, idempotent tasks/reminders/messages,
  plan usage, atomic conditional reservations, conservative unknown-cost settlement, signed/deduped
  inbox and version-aware billing sandbox events, durable run/outbox rows, redacted admin endpoints.
- ModelLab: validates/protects the 60-case bank, imports, grades exact JSON, preserves null/provenance,
  runs a bounded fake provider, persists SQLite evidence, reports JSON/CSV/Markdown/HTML/SVG and
  writes non-promoting router drafts.
- Owned channel: responsive accessible shell wired to the synthetic local backend.

## Validation

- Ruff plus repository secret scan: PASS 2026-09-10.
- Strict mypy over 15 source files: PASS 2026-09-10.
- Unit/ModelLab/web: 19 passed; API E2E: 6 passed; two upstream TestClient warnings.
- Alembic clean bootstrap and no-drift check: PASS on fresh SQLite database.
- ModelLab offline demo: PASS; 60 cases validated, bounded five-case run, one injected failure,
  all five report formats and non-promoting router draft produced.
- Browser: local page loaded, synthetic account usage appeared, one draft journey completed and
  showed `Completed`; server logs showed successful root/token/usage/message requests.
- Browser CLI from the verification skill was unavailable; Windows computer-use fallback was used.
- Docker Compose config: PASS. PostgreSQL/Redis integration: NOT RUN because Docker Desktop engine
  did not become ready after launch; no mock was substituted.

## Blockers

- WhatsApp live launch: blocked by current eligibility evidence for the intended India audience.
- Live providers, payment sandbox, deployment, real messages and paid benchmarks: not authorized/configured.
- Real PostgreSQL/Redis concurrency and restore evidence: blocked by the unavailable Docker engine.
- Full admin UI, production OIDC, remote-action reconciliation, complete context/routing/recovery,
  queue workers, payment-provider sandbox and live deployment are not implemented.

## Review

- Supervisor rejected candidate `5342079` with P0 production sandbox/placeholder-secret exposure,
  P1 ModelLab CSV formula injection, P2 first-use platform-budget race and P2 silent unknown-case
  omission. All findings were accepted and remediated with regressions; see `docs/reviews/INT-001.md`.
- Supervisor rejected candidate `f88c0ca` because the documented production secret placeholder and
  whitespace/control-prefixed CSV formulas still bypassed the first repairs. Both findings were
  accepted and remediated with regressions; see `docs/reviews/INT-002.md`.
- Supervisor rejected candidate `4dd48af` because whitespace-only secrets bypassed the new length
  check. The finding was accepted; trimmed content is now measured and both secret fields have
  regressions. See `docs/reviews/INT-003.md`.
- Supervisor accepted exact commit `ad3b54e` for the local development milestone; see
  `docs/reviews/INT-004.md`. This is not Core v1 or production acceptance. PostgreSQL execution
  evidence for the race remains blocked.

## Next three actions

1. Start Docker engine and run `python scripts/tasks.py test-integration` without a mock substitute.
2. Implement the incomplete Phase 4–7 production-auth, worker, reconciliation and admin surfaces.
3. Configure approved providers/billing/channel/deployment, then execute the remaining release gates.

## Mobile client (Flutter, `mobile/`)

- Updated: 2026-09-26. Branch `Kashyep/flutter-mobile-client` (fast-forwarded to `67e478b`).
- Plan: `docs/UI_IMPLEMENTATION_PLAN.md` §2–8; decision: ADR-0002. Cards: MOB-001…MOB-013, API-001.

### History (earlier on 2026-09-26, commit `67e478b`)

- Phase 0: ADR-0002 and the Design.md token/font supersession.
- Flutter 3.47.5 installed; `flutter create` scaffold with first-pass lib/ code (no tests, no fonts;
  `flutter analyze` then reported 8 issues). The earlier note "Phase 1-4 Complete" overstated this.
- Android toolchain installed: JDK 17 at `C:\Users\kashy\AppData\Local\Android\jdk-17`, SDK at
  `C:\Users\kashy\AppData\Local\Android\Sdk` (user env vars; fresh agent shells may need
  `JAVA_HOME` exported). A debug APK of the first-pass client (`ai.karmi.karmi_app`) ran on the
  Pixel 9a (`5B271XEBF3XDF0`) with Impeller/Vulkan.

### Verified state (this session)

- Housekeeping: IDs `ai.karmi.app` (Android + iOS), `web/` and `windows/` removed, IDE files ignored.
- Fonts bundled (hash-verified against google_fonts 8.2.1), OFL registered, runtime fetching off.
- Theme/glass/motion/high contrast, typed API client, session (`/dev/token`), shell + Chat, Tasks,
  Usage, Memory, Settings, Welcome, Plans, confirmation-sheet stub. Backend `GET /v1/tasks` (API-001).
- Gates PASS locally: format, analyze (0 issues), `flutter test` 257 (183 + 74 goldens),
  `flutter build appbundle --release`; same format/analyze/tests/goldens PASS in an `ubuntu:24.04`
  container with Flutter 3.47.5. Python lint/typecheck/test-unit (32)/test-e2e (15) PASS.
- Evidence: `docs/release-evidence/mobile-2026-09-26.md`.
- Independent verifier (Gemini 3.8 Flash High, read-only) re-ran format/analyze/`flutter test`
  (257) and `test-e2e` (15) and checked IDs, fonts, placeholder removal, chat split, Outcome enum,
  CI parity, task scoping, glass-surface usage and evidence honesty: ACCEPT, no discrepancies.
- Work is uncommitted in the working tree (no commit requested).

### Decisions

- Goldens stored per host OS (`mobile/test/goldens/{windows,linux}`); CI compares Linux.
  Linux baselines are generated in Docker (image `karmi-flutter:3.47.5`, built locally from the
  official Linux archive; Docker Desktop must be started first).
- liquid_glass_widgets shaders do not load under `flutter test`; goldens show the fallback render.
- Reduce transparency swaps the whole shell to opaque Material bars, not just `KarmiGlassSurface`.
- `GlassTabBar` bar-level gesture node is unlabelled; wrapped in a "Main navigation" container.
- Send control is a Material 48dp button inside the glass tray (no glass-in-glass).

### Device release gates (2026-09-26, later session)

- Committed `4492857`, pushed, PR #17: CI `checks`, `mobile-checks`, `mobile-ios-build` all passed
  (run 36241854319).
- Pixel 9a gates run on profile builds against the local backend: startup, input latency, Chat
  scroll frames, reduced motion, OS contrast, font scale 2.0, keyboard and TalkBack (tree + touch
  exploration) all PASS after fixes. Numbers are in `docs/release-evidence/mobile-2026-09-26.md`.
- Seven device failures fixed under MOB-014, each reproduced first by a failing test (send icon,
  app-bar platter, transcript lost on toggle, card semantics, glass menu a11y, focus visibility,
  theme selected state). These fixes are **uncommitted** and not yet through CI.
- Gates: `flutter test` 273 passing (Windows), Linux container 199 + 74 goldens, analyze 0 issues,
  format clean, appbundle 51.3 MB. Goldens were regenerated for both OSes (28 changed each).
- Findings: Android "High contrast text" does not reach Flutter (only Contrast level: High does);
  adb-injected TalkBack swipes are not recognised; goldens must run as a whole file (a single glass
  settings golden differs when run alone).
- Device settings changed for testing were restored and read back. During one step, a stray tap
  after the app had closed opened Google Calendar on the device; nothing was changed there.

### Blockers / NOT RUN

- iOS: VoiceOver, local iOS build, iPad keyboard: no Mac/iOS device. CI iOS job passed only at `4492857`.
- TalkBack swipe traversal and spoken output (including live-region announcements) were not observable over adb.
- No low-end reference Android device named (Q8); performance was measured on the Pixel 9a only.
- Backend gaps: no structured `ASK_USER` payload (confirmation sheet is a stub), no plan catalogue,
  no chat history, no production auth (Q3). T3.3 owner screenshot sign-off pending.

### Next three actions

1. Commit the MOB-014 fixes and push so CI (including `mobile-ios-build`) runs on them.
2. A person runs TalkBack swipe/speech and VoiceOver on real devices; record in the evidence file.
3. Owner reviews goldens (T3.3); backend card for a structured `ASK_USER` action payload.

## Tier themes, Liquid Glass and Armory (2026-09-27)

- Source: `docs/design/implementation_plan.md`, `docs/design/karmi_tier_color_palettes.md`
  (merged via PR #19; this branch was fast-forwarded to `9f6e726`, no commit made).
- Cards: API-002 (server `unlocked_tier`/`active_theme` + migration `8a4f2c9e1b3d`), WEB-002 (web
  shell tokens/glass/Armory/dynamic manifest), MOB-015 (Flutter tiers, Armory, native icons).
- Tokens for all 8 tier × mode combinations are generated from the palette doc by
  `mobile/tool/derive_theme_tokens.py` (Dart + CSS + audit JSON); icons by
  `mobile/tool/generate_app_icons.py` from watermark-cleaned masters in `docs/design/assets/icons/`.
- Tier 4 display label is now "Parth" (plan id stays `part`); the misspelling guard is
  `tests/unit/test_tier_spelling.py`.
- Local dev DB `data/development.db` was stamped at `73075806233f` and upgraded to head (backup
  of the pre-migration file at `%TEMP%/development.db.bak`); synthetic account restored to Ananta.
- Android icon switch verified on the Pixel 9a: applied on `onStop` because disabling the running
  alias destroys the task (first attempt crashed); iOS alternate icons NOT VERIFIED (no macOS).
- Plan's "Niriksh" framework does not exist in this repo; its tests map onto pytest + flutter_test.


### Tier-theme verification (2026-09-27)

- `python scripts/tasks.py lint`, `typecheck`, `test-unit` (47), `test-e2e` (22),
  `test-integration` (2; PostgreSQL/Redis via Docker) PASS.
- Flutter 3.47.5: `dart format --output=none --set-exit-if-changed .` (0 changed),
  `flutter analyze` (0 issues), `flutter test` (319 incl. 90 Windows goldens),
  Linux Docker `flutter test --tags golden` (90), and
  `flutter build appbundle --release` (52.0 MB) PASS.
- Regenerated icons with `python mobile/tool/generate_app_icons.py`; all four tiers
  completed. An initial attempt raced a concurrent Gradle build and could not
  write an iOS icon file; rerunning after the build succeeded.
- `python mobile/tool/derive_theme_tokens.py` produced WCAG text minimums of
  4.51–6.29 across the eight combinations. The generated CSS and Dart tokens
  share that source; tests audit surface, glass, disabled, and focus contrast.
- The Android alias/icon switch was exercised on the Pixel 9a with a local
  synthetic account. No iOS device validation; alternate icon bridge remains
  NOT VERIFIED at runtime. No paid checkout, provider call, or customer message.

### PR #20 Armory contrast follow-up

- CI run `36311395158`, job `108597892680`: three Linux
  `textContrastGuideline` failures reported for the gallery and Ananta/Yanta
  light. Independent token checks passed; Linux pixel inspection found
  Yanta's dark tagline ink `#050806` on white, but Flutter's inflated text
  sampling rectangle included 37 pale pixels from the status chip just above
  it (more than the 34 fully dark glyph pixels). Added 8px separation between
  chip row and tagline; no palette, text token or a11y assertion changes.
- Post-fix: Windows and Linux Docker `flutter test --exclude-tags golden`
  229/229 each, `flutter analyze` 0 issues, `dart format` 0 changed.
  Regenerated only 8 tier Armory goldens per OS; both golden suites 90/90.
  CI had not run on this fix at the time of local verification.

## Backend setup (2026-10-10)

- Added hidden URL prompts and exclusive owner-only .env creation; auto-generates local auth/webhook secrets. Existing .env preserved; no credentials entered this session.
- Fixed Alembic percent escaping for encoded URLs. Runbook covers migrations, workers and USB mobile connection.
- Checks: 20 targeted tests, lint/secret scan, typecheck and disposable fresh migration/HTTP smoke PASS. Independent review: docs/reviews/SETUP-001.md.
- No production deployment or live generation. Clerk and physical-device setup continued below.

## Neon connection slice (2026-10-10)

- Operator confirmed pooled Neon read-only test: neondb, PostgreSQL 18.6. Agent has no credentials in conversation; private URLs are saved locally.
- With explicit user authorization, Alembic initially upgraded empty production branch to c5d7e9f1a2b4; 20 tables verified. Later, on 2026-10-10, user explicitly authorized reviewed Clerk migration 1a2b3c4d5e6f. Preflight confirmed expected prior revision, helper applied only that revision, and postflight verified 20 tables, column/unique constraint and target revision. No app deployment or live model call.
- Added separate direct migration URL, psycopg normalization, Neon verify-full TLS and pool 2/overflow 0/timeouts 15s. Disabled PostgreSQL create_all in API/worker/helper.
- Added python -m scripts.setup_neon: hidden paired URL prompts, separate ignored owner-only .env.neon, no connection/writes. `.env.neon` is not auto-loaded.
- 104 local tests, lint/secret scan and typecheck PASS. Independent review docs/reviews/NEON-001.md accepts. Read-only Neon inventory with strict TLS succeeded using Certifi roots; no migrations or application startup against Neon.
- Changes remain local on readiness-harness; not pushed to main. Preserve prior setup changes. Next: operator saves URLs; read-only inventory; review migration plan before any production write.

## Clerk backend auth slice (2026-10-10)

- Current checkout branch: `readiness-harness`; preserve all earlier uncommitted setup work.
- Operator saved `.env.clerk`; confirmed owner-only mode and expected variable names without printing values. Runtime settings successfully parsed the Clerk RSA verification key.
- Added PyJWT RS256 verification, issuer/expiry/iat/session checks, immutable `sub` mapping, customer-only first-login provisioning with Ananta/free subscription, and safe concurrent-provision retry. Existing development HMAC flow remains local-only.
- Added nullable unique `users.clerk_subject` and reversible migration `1a2b3c4d5e6f`. Fresh disposable SQLite upgrade + `alembic check` PASS. After explicit authorization, Neon advanced from `c5d7e9f1a2b4` to `1a2b3c4d5e6f`; runner verified 20 public tables and the Clerk column/unique constraint.
- Neon migration helper accepts only empty schema / expected `c5d7e9f1a2b4` / verified current target, pins command to `1a2b3c4d5e6f`, and verifies one-column UNIQUE on `clerk_subject`. Pure preflight tests and independent read-only review pass.
- 87 unit/ModelLab/web tests and 29 API E2E tests PASS; Ruff/secret scan and strict mypy PASS. Independent read-only review `docs/reviews/CLERK-001.md` ACCEPT_RECOMMENDED for auth and migration helper.
- Offline public-key verification cannot observe session revocation until JWT expiry. No deployment or live provider activity.
- Next: operator signs in on device, then we start/test the intended local backend path. Do not start the app against Neon without explicit authorization.

## Flutter Clerk client and USB install (2026-10-10)

- Added `clerk_flutter 0.0.18-beta`; Clerk sessions persist through the SDK, and the API client fetches a fresh token per request. Stale development tokens cannot fall back into Clerk mode. Local `/dev/token` remains for unconfigured builds/tests.
- Added private-config launcher `mobile/tool/run_android_dev.py`; it reads only the Clerk publishable key from `.env.clerk`. Backend PEM stays out of Flutter. USB URL is `127.0.0.1:8000` via `adb reverse`.
- Pixel 9a (`5B271XEBF3XDF0`) initially needed USB-debug authorization; after authorization built and installed debug APK successfully. Final installed build has API URL `http://127.0.0.1:8000`; `adb reverse tcp:8000 tcp:8000` is active. Package `ai.karmi.app` was running; Clerk sign-in panel appeared in screenshot, still Development mode. No sign-in/API request was made.
- Flutter analyze and 231 non-golden tests PASS; targeted screens tests 29/29 PASS. First full suite: 313 passed, 8 Usage-screen Linux goldens failed; all other goldens passed. APK debug build PASS. Full golden differences need review; not refreshed.
- Next: operator completes Clerk test-account sign-in; then run local backend with development DB and verify `/ready` + one authenticated API request. Keep Neon runtime separate until explicitly authorized.

## Goal paused checkpoint (2026-10-12)

- User explicitly asked to stop and resume later. Goal remains paused; no commit/push/deploy/release.
- Durable status and ordered remaining work: `docs/PROGRESS-2026-10-12.md`.
- OpenCode adapter/runtime/harness edits were added immediately before the pause and remain unverified:
  `src/daily_agent/opencode.py`, `src/model_lab/opencode_runner.py`, changes to config/services/API/router/CLI, and `tests/unit/test_opencode.py`. No tests or lint ran after these edits. Reinspect current diff and verify before relying on them.
- No OpenCode key was read and no provider request was made. Continue only with synthetic prompts and explicit bounded free-model requests; keep runtime disabled until privacy, evaluation and routing evidence gates pass.

## Release 1 chat redesign (2026-10-21 to 2026-10-22, branch release1/chat-redesign, HEAD 4b95f5c)

- Verified: contract v1 (`docs/release1/EXECUTION_CONTRACT.md`, 5de20a8), discovery `docs/release1/discovery/01–05`, `DEPENDENCY_BOARD.md`, `SCOPE_TIMELINE.md`, `R1_1_BACKLOG.md`, `TEST_STRATEGY.md` exist. Deviations D1–D7 are in contract §0 and mapped to R1.1 tickets.
- Verified (git log): 63 commits `dcf4f75..4b95f5c` (54 non-merge, 9 merge). Diff stat `dcf4f75..4b95f5c`: 223 files, +23,847 / −660. Squads P1, F, A, B, BW, C, D, E, G, Phase 2 Wiring, QA-gap, FIX are merged on the branch.
- Verified (re-run 2026-10-22 at 4b95f5c): `make` lint clean; typecheck 49 files clean; `test-unit` 226 passed; `test-e2e` 62 passed; `test-integration` 6 passed (podman, postgres:17, redis:8). Baseline pre-R1: unit 166, e2e 51.
- Reported by Supervisor at HEAD 4b95f5c (not re-run here): `flutter analyze` clean; a11y and chat suites 103 passed. Full Flutter suite (goldens included) final count: from the Supervisor's run, recorded in `docs/release1/QA_REPORT.md` when received.
- Backend audit 10/10 fixed with regression tests. Client audit: AUDIT-01/02 in `147b1ee`, `90586b6`; AUDIT-03/04/05 in `4b95f5c`. AUDIT-02 residual: two accounts on one device without sign-out share `draft.v1.new`.
- Perf: host-VM proxies only (`docs/release1/perf/AFTER.md`, measured at `e9dd199`). Filtered rebuilds per send median 9 → 20 (regression signal; batching claim NOT supported). Device/profile frame timings, streaming frame timing, APK size, backend p50 are NOT MEASURED.
- Goldens: 27 regenerated under `mobile/test/goldens/linux/` plus 1 new. Not visually reviewed (R-9).
- `docs/release1/RELEASE_REPORT.md` rewritten as final (no DRAFT). `docs/release1/QA_REPORT.md` verdict updated to Boss rejection round 1: resubmitted, not signed off by QA. Sign-off blocked on PENDING-USER items (device/emulator, real provider and model, auth sign-in, onboarding): none run, none passed.
- R-6 resolved by Supervisor: Artifact and Sources drawers deferred to R1.1 (inside R1.1-5). R1 keeps inline citation chips and file cards.
- No production deploy, migration, live charge, or real message. R1.1 NOT started. Untracked `Claude outputs/` and `docs/release-evidence/device/*.png` preserved; `docs/release-evidence/device/01-launch.png` shows modified in the working tree and was not changed by this work.

