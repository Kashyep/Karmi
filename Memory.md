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

### Blockers / NOT RUN

- Pixel 9a disconnected mid-session; owner chose to skip device checks: TalkBack, hardware
  keyboard, OS font scale, OS reduce-motion/contrast, TTFF, input latency, glass frame budget.
- iOS build, VoiceOver, simulator: no macOS host. GitHub Actions run not observed.
- Backend gaps: no structured `ASK_USER` payload (confirmation sheet is a stub), no plan catalogue,
  no chat history, no production auth (Q3). T3.3 owner screenshot sign-off pending.

### Next three actions

1. Reconnect the Pixel 9a and run the §8 manual/perf checks; record them in the evidence file.
2. Push the branch and confirm `mobile-checks` (ubuntu) and `mobile-ios-build` (macOS) are green.
3. Owner reviews goldens (T3.3); backend card for a structured `ASK_USER` action payload.

