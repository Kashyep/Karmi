# Daily Agent implementation memory

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

## Routing, telemetry and signed policy loop (2026-09-27, 14:20 UTC)

- Baseline `00b7224`, clean before this work; branch `Kashyep/routing-telemetry-loop`.
  Commits listed below. ADR-0003, `docs/task-cards/{RTR,TEL,ART}-001.md`,
  `docs/runbooks/routing-telemetry.md` and generated `docs/contracts/` describe the scope.
- Implemented hard eligibility, static/shadow/LinUCB/canary routing, provider health, signed
  PolicyBundleV1 verification/store/rollback, guarded harness selection, pseudonymous
  non-blocking telemetry, finalization/export/retention and authenticated feedback/admin
  endpoints. Default static route preserves the local response in synthetic E2E;
  provider failure keeps known/unknown costs, failed actions retain provider expense
  while refunding customer usage, and router crashes recheck eligibility. Signed
  JSON rejects ambiguous duplicate keys (failing-before/passing-after test).
- Source candidate committed as `08e4c7b` (87 files) plus test-sink fix `0d96aa3`, then a
  remediation commit `7c0fe49` (telemetry writer batching + security findings F1–F9). Pushed
  to `origin/Kashyep/routing-telemetry-loop`; no PR opened, no deploy.
- PR #22 CI (run 36344052976) failed 9 unit tests on the merge with `main`. Causes: `main` #21
  renamed plan id `part`→`parth` (routing `TIERS` and tests still used `part`), and
  `tests/unit/telemetry/test_cli.py` had used the default `./data/development.db`, whose tables
  only existed locally. Fix: merged `origin/main`, renamed the tier to `parth` in routing and
  tests. The CLI tests now run on a temp Alembic-migrated DB with a seeded run. That exposed and
  fixed a `telemetry status` naive/aware datetime crash on SQLite. Telemetry models/migration
  were already present; no schema change.
- VERIFIED on the final tree (2026-09-27, local Windows/Python 3.14.3, Docker 29.6.1):
  `python scripts/tasks.py lint` PASS, `typecheck` PASS (50 files), `test-unit` 220,
  `test-e2e` 41, `test-integration` 2 (PostgreSQL/Redis). Regression tests for F2–F9 and the
  writer batch dedupe failed on `0d96aa3` in a throwaway worktree and pass now. A CLI smoke on a
  temp store showed quarantine, the no-op re-promote and deactivate→rollback staying static.
- Latency (100 req, concurrency 4, before remediation; hot path unchanged by it): SQLite
  baseline 17.2/289.87 ms p50/p95, 53.67 rps vs candidate 18.81/351.84, 45.89. Disposable
  PostgreSQL runs: baseline 79.58/149.55, 45.7 and 75.17/126.55, 49.52; candidate
  91.32/146.31, 41.59 and 90.93/139.81, 41.22. The extra SQL runs on the telemetry writer
  thread. `docs/release-evidence/routing-telemetry-2026-09-27.md` has the details.
- Reviews (task-tool subagents; Orca Antigravity workers can't launch because `agy` is missing):
  - verifier: ACCEPT.
  - security: REWORK F1–F9 → re-review: F2–F4, F6–F9 RESOLVED; F1 PARTIAL/contained; F5 PARTIAL.
  - Follow-ups: in-flight feedback emit dedupe and N2 chunked actor purge (both done); N1 older
    builds reject the new `state.json` field (fail-closed; documented).
- Decisions:
  - Live provider spend is hard-disabled (`providers.LIVE_PROVIDER_SPEND_VERIFIED=False` →
    eligibility `provider_spend_unverified`; the client refuses to construct).
  - Messages over 20k characters get a 413 before a budget hold.
  - No-route is a 503 with Retry-After and no persisted Run.
  - A DEFERRED provider fault refunds the customer and keeps the expense.
  - Rollback quarantines the failing version, persisted in `state.json`.
- NOT VERIFIED / blocked:
  - F1 worst-case reservation: needs verified TypeSafe billable rates, a max-output/retry bound
    and spend authorisation. The single-call estimate and `min(cap, estimate)` clamp remain.
  - Feedback per-principal rate limit and spool size cap: not built.
  - Parakh consumer (repo absent), concurrent-money/restore gates, device/manual gates, production
    migration/deploy. Live calls, checkout and WhatsApp remain disabled.
- Next: obtain verified TypeSafe pricing/bounds and approval before any live-spend change;
  run Parakh ingestion against a real export; decide on a feedback rate limit.
