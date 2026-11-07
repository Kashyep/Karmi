# Daily Agent implementation memory

## Release 1 final — release-prep state (2026-11-08)

- Release preparation branch `r1f/release` in worktree `/home/rosso/Projects/Karmi-release/final-rel`, base `314afa4` (`release1/final`).
- Commits in this release preparation sequence:
  - `26aac94` `chore(release): bump mobile version to 0.1.0+5` (version bump)
  - `256a6e9` `docs(release): add changelog, release notes, sha256 and signing recipe` (release documentation round 1)
  - `a955b91` `docs(release): owner runbook for deploy, migration, SSO, and scrub decisions` (owner runbook `docs/release1/OWNER_STEPS.md`)
  - Docs commit (this commit): `docs(release): PR draft and memory state for release 1 final` (`docs/release1/PR_DRAFT.md`, `Memory.md`)
- Version verification: `mobile/pubspec.yaml` verified on disk as `0.1.0+5`.
- Release scope items 1–9 verification state:
  - **Item 1 (Admin backend additions & controls)**: VERIFIED (Backend) / Web UI NOT MERGED. Backend endpoints and monitoring metrics verified in `tests/unit/test_admin_bug_reports.py`, `tests/unit/test_admin_api.py`, `tests/e2e/test_admin_api.py` (commits `ac3d16e`, `64a70dc`, `e629d57`). Web admin dashboard UI remains on branch `r1f/webadmin`. Device/browser check: NOT VERIFIED (device testing paused by owner).
  - **Item 2 (Measured optimization)**: NOT VERIFIED. Optimization work remains on branch `r1f/perf` and is NOT MERGED into `314afa4`. Baseline recorded in `docs/release1/perf/BASELINE.md`. Device timing: NOT VERIFIED (device testing paused by owner).
  - **Item 3 (Loading motif & skeletons)**: VERIFIED. `KarmiTypingDots` and `KarmiSkeleton` verified in `mobile/test/widgets/karmi_typing_dots_test.dart` and `mobile/test/widgets/karmi_skeleton_test.dart` (commit `5db031e`, `ec578d6`). Device check: NOT VERIFIED (device testing paused by owner).
  - **Item 4 (Google Sign-in / SSO via Clerk OAuth)**: PARTIALLY VERIFIED. Mobile UI and deep-link handling verified in `mobile/test/auth/google_sign_in_button_test.dart`, `mobile/test/auth/clerk_sso_test.dart`, `mobile/test/auth/account_auth_google_test.dart`; backend identity mapping verified in `tests/e2e/test_clerk_sso_identity.py` (commits `a7479ef`, `65a79a2`; runbook in `docs/release1/GOOGLE_SSO.md`). Real Google sign-in and device testing: NOT VERIFIED (device testing paused by owner).
  - **Item 5 (Money & INR representation)**: VERIFIED. Decimal/sub-micro formatting and INR plan pricing verified in `mobile/test/widgets/money_test.dart`, `tests/unit/test_money.py`, `tests/unit/test_plans.py` (commits `ac3d16e`, `6a5a7f2`, `b8bfc83`, `55a2bfe`). Device check: NOT VERIFIED (device testing paused by owner).
  - **Item 6 (Bug reporting system)**: VERIFIED. Database migration `a5b6c7d8e9f0` (`migrations/versions/a5b6c7d8e9f0_bug_reports.py`), backend tests (`tests/unit/test_bug_reports.py`, `tests/integration/test_bug_reports_pg.py`), and mobile client queue/UI tests (`mobile/test/features/bug_report/`, `mobile/test/features/chat/error_card_bug_report_test.dart`) verified (commits `ac3d16e`, `6a5a7f2`). Device check: NOT VERIFIED (device testing paused by owner).
  - **Item 7 (Unified shell layout)**: VERIFIED. Single layout tree and 12 golden tests verified in `mobile/test/shell/shell_parity_test.dart` (commit `f6617d0`, `66e0253`). Device check: NOT VERIFIED (device testing paused by owner).
  - **Item 8 (Error card copy rewrite & jump pill)**: VERIFIED. Plain single-sentence copy and jump-to-latest pill verified in `mobile/test/features/chat/empty_state_test.dart` and `mobile/test/features/chat/jump_pill_test.dart` (commit `f6617d0`, `3cbc0b0`, `bcd3967`, `c322f17`). Device check: NOT VERIFIED (device testing paused by owner).
  - **Item 9 (Web admin dashboard additions)**: PARTIALLY VERIFIED. Backend routes and CSP hardening verified in `tests/e2e/test_admin_api.py` and commit `2a37177`. Web admin UI frontend is NOT MERGED (in branch `r1f/webadmin`). Device and browser testing: NOT VERIFIED (device testing paused by owner).
- Pending integrations and reconciliation items: See `docs/release1/PR_DRAFT.md` section `## RECONCILE (supervisor)` for the list of unmerged branches (`r1f/webadmin`, `r1f/perf`, `r1f/release`).
- Owner decisions still open (deploy, migration `a5b6c7d8e9f0`, Clerk Google SSO configuration, PR #34, issues #39–41, public repo scrub, Pixel release reinstall): See runbook `docs/release1/OWNER_STEPS.md`.
- Constraints adhered to: No push, no PR creation, no live migrations or deployments executed; no secrets, IPs, Clerk IDs, or keystore material recorded.

## Active Release 1 chat redesign resume (2026-10-23)

- Integration checkout `/tmp/wt2-int`, branch `release1/integration`, HEAD `eedb13b`.
  No push, PR, deploy, hosted migration or live provider call has happened.
- Integrated and gate-verified: P1 long context, P3 reply rendering, P4 tester
  metadata (merged with P1 history plumbing), P5 composer/status (offline-retry
  regression fixed so transport retries resume the idempotent start request and
  only server-terminal failures use `/v1/chat/continue`), P6 app bar/banner,
  P7 jump-to-latest, P9 suggestion chips, P10 quality corpus, device harness
  (`scripts/dev_fake_provider.py`, `scripts/device_smoke.py`).
- Verified gates on `eedb13b`: `ruff check` clean, `mypy` clean (49 files),
  256 unit + 84 e2e passed, `flutter analyze` 0 issues, `dart format` clean,
  766 Flutter tests passed. Goldens regenerated for the merged UI and the
  branding change; owner visual review (R-9) still pending.
- Branding: assistant replies are always "Karmi" with a code-drawn logo
  (`mobile/lib/widgets/karmi_logo.dart`). Served model/provider names are no
  longer rendered anywhere, including the tester diagnostics line.
- Local run verified: fake provider on 127.0.0.1:8900, backend on 127.0.0.1:8001
  with a fresh SQLite DB, `/v1/chat/stream` streams fake markdown; the backend
  refuses openrouter.ai. Debug APK rebuilt with the branding change.
- NOT verified: the branding build on the Pixel 9a (USB disconnected during the
  final install), P8 attachment-control removal (kept for an owner decision),
  local test auth (`.env.testauth` code never supplied), host-level
  free-model exclusions (P2 kept reverted by owner request).
- Do not read `.env.testauth`; no live provider spend, paid call, release PR,
  production action or unverified device claim has occurred.

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


## Release 1 integration (2026-10-23, branch release1/integration, worktree /tmp/wt2-int)

- Merged into integration: P1, P3, P4 (debug meta + history; 3 conflicts resolved keeping `history` and `debug_enabled`), P5, P6, P7, P9, P10, and the device harness (`scripts/dev_fake_provider.py`, `scripts/device_smoke.py`, `docs/release1/DEVICE_TESTING.md`). Base HEAD before this entry: `a89fe20`.
- Reply identity (owner correction): replies show a provider nickname + generated avatar, never the product name and never the raw model id. `mobile/lib/features/chat/provider_identity.dart` (new); `message_bubble.dart` header/semantics label; `debug_meta_line.dart`; `karmi_logo.dart` removed. Backend exposes `model` on `MessageView`/`ChatMessageView`, on history (join on `Run.served_model`) and on `run.finished`.
- Tasks tab now routes to `TasksComingSoonScreen` (`karmi_shell.dart`); `TasksScreen` is retained but unexercised by widget tests until the real feature lands.
- Retry fix `56f71cb`: transport failures resume the idempotent start request (`clientMessageId`); only server-backed terminal failures use `/v1/chat/continue`.
- Golden set regenerated for chat (provider header) and tasks (construction page), Linux host goldens. Owner visual review R-9 still pending.
- `screens_test.dart` deliberately skips `textContrastGuideline` for the tasks placeholder: the guideline reports a false 2.66:1 while the render-tree style is `#050806` on `#F2F7F4` (18.9:1) and is unchanged by text/card/background edits. Tap-target and labelling guidelines still run. Documented in the test and in `release_completion.md` §3.1.
- Not verified: device pass after the provider-identity change (Pixel 9a `5B271XEBF3XDF0` dropped off USB); local test auth (needs owner's test code in ignored `.env.testauth`).
- Open owner decisions: P2 free-pool exclusions (reverted at `f5d2794`), composer attachment button (kept), iOS distribution, Android release keystore, public repo for Obtainium, golden review, analytics/admin scope.
- Handover document: `release_completion.md` (repo root; copy also at `/home/rosso/Projects/Karmi/release_completion.md`).
- Final gates at the tip of `release1/integration` (2026-10-23): `flutter analyze` clean, `flutter test` 767 passed; `.venv/bin/ruff` clean, `.venv/bin/mypy src` clean (49 files), unit 256 passed, e2e 85 passed. Backend tools live in `.venv/bin` — bare `ruff`/`pytest` are not on PATH.

## Release 1 final evidence (2026-10-24)

- Azure regression 12-case suite: commit `7145bb8`; 11/12 cases passed. The profile 404 was fixed in `ba3198c` and is pending redeploy.
- Admin edit backend: `r1/admin-edit` commit `a38f8f8`; audited and reworked.
- Onboarding hardening: commit `ba3198c`.
- Release signing: commit `f8e0ad4`; signing key is at `~/.karmi-keys` with a backup.
- Documentation: commit `7baafb9`.
- Admin web UI: commit `c9e87d2`; browser verification is in progress.
- Admin app UI: commit `153a7fb`; tests are in progress.
- Remaining release gates are pending: Azure redeploy, release APK/AAB, Pixel smoke, user admin-code enrollment, and release approval.

## Release 1 status update (2026-10-24, later)

- Integration tip `f375410` on `release1/integration` (local only; not pushed).
- Azure `karmi-beta` runs `f8865ac` (Healthy, 1 replica). Neon migrated to head `f4a5b6c7d8e9`. Regression 12/12 (`docs/release-evidence/r1-azure-regression-3.md`).
- Fixes since the last entry: admin edit/tier expiry backend (audited, reworked); credit adjustments durable (`credit_adjust_micro`, `0b2f80d`); daily quota regression from `0ed052f` fixed (`13f9821`, audited RELEASE-OK); app Promote/Demote preset adjacent tier; web admin audit fixes (`7287565`); onboarding text-slot fix + goldens.
- Gates at tip: ruff and mypy clean; pytest unit+web and e2e 0 failures (run separately: duplicate `test_quality_corpus.py` basename); flutter analyze clean; flutter test 855 passed.
- Release artifacts v0.1.0+4: `~/Projects/Karmi-release/v0.1.0+4/` (APK sha256 c479c99e…7b606, AAB 9c34c66f…171af). Signed with `~/.karmi-keys/karmi-release.jks` (cert SHA-256 14a65fff…8ba1); release build fails loudly without `mobile/android/key.properties`.
- Pixel 9a: old debug-signed app uninstalled (user approved); v0.1.0 code 4 installed; launch screenshot `docs/release-evidence/device-r1/01-release-launch.png`.
- Ops notes: this host's IPv6 route to Neon hangs, so deploy/migrate use `PGHOSTADDR=<neon-proxy-ip>`; use `TMPDIR=~/.cache/karmi-tmp` for tests (`/tmp` is a 7.7G tmpfs); `karmi-ui` (`~/.local/bin`) opens the live admin, `karmi-ui code` enrolls the admin code.
- PENDING (user): rossoadmin sign-in + admin code enrollment, device smoke of onboarding and admin, release approval. Not pushed, not published.

## Release 1 update (2026-10-24, onboarding + admin access fixes)

- User device report: onboarding asked only for an email code; Welcome "Sign in" opened Create; code paste broken; Sign in button dead.
- Fixed on `r1/onboard-auth` (merged): Create account = names, username, email, password (Clerk requires username+password) then email code; one hidden OTP input (paste/autofill); Welcome sign-in opens Sign in mode; after password Clerk returns `needs_second_factor` (new-device check) and the app now calls `sendSignInCode` then shows the code field; unknown sign-in states show an error. Preferences step asks only the model approach (no language/Indonesian). Test fake now matches real Clerk. Flutter: analyze clean, 884 tests passed.
- Admin access root causes: (1) `deploy_azure.py deploy` replaced env vars without `DAILY_AGENT_ADMIN_CLERK_USER_IDS` (wiped allowlist) — fixed in script, allowlist now read from `.env.clerk`; (2) `users.role` was `customer` for both allowlisted users — set to `admin` in Neon with `admin.role_granted` audit rows (runbook-sanctioned direct DB step); (3) image `f8865ac` never reached ACR; Azure now on `34f4062`.
- Azure regression 4 on `34f4062`: 12/12; allowlisted admin gets code-required (200), true non-admin 403.
- Final artifacts (rebuilt from `b9a4457`): `~/Projects/Karmi-release/v0.1.0+4/` APK sha256 d57138ec…f34b2, AAB 43ae4e1b…37802; installed on Pixel 9a.
- PENDING (user): `karmi-ui code`, rossoadmin sign-in on device, admin console check, release approval. Nothing pushed or published.
