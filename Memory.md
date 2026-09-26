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

## Mobile Client Initialization (2026-09-26)

- **Phase 0 Complete**: 
  - ADR-0002 created in `docs/decisions/` recording Flutter as the mobile choice and resolving Q1-Q9.
  - `Design.md` token table updated to the Karmi green palette and Exo/Proza Libre/Trykker typography, superseding the original blue tokens.
  - Task cards `MOB-001`, `MOB-002`, `MOB-003` created in `docs/task-cards/` for Phase 1-3.
## Mobile Client Initialization (2026-09-26)

- **Phase 0 Complete**: 
  - ADR-0002 created in `docs/decisions/` recording Flutter as the mobile choice and resolving Q1-Q9.
  - `Design.md` token table updated to the Karmi green palette and Exo/Proza Libre/Trykker typography, superseding the original blue tokens.
  - Task cards `MOB-001`, `MOB-002`, `MOB-003` created in `docs/task-cards/` for Phase 1-3.
- **Phase 1-4 Complete**:
  - Flutter SDK 3.47.5 was successfully installed and added to the path.
  - Initial scaffolding via `flutter create` executed. 
  - Required Dart files for Phase 2, 3, and 4 (`karmi_colors.dart`, `karmi_theme.dart`, `karmi_glass.dart`, `karmi_api.dart`, `chat_screen.dart`, etc.) written and properly formatted.
  - Dependency errors and API mismatches (e.g. `liquid_glass_widgets` v1.6.2 parameters) were identified by `flutter analyze` and fixed.
  - `dart fix` applied for lint compliance.
- **Android Toolchain Setup (2026-09-26)**:
  - Discovered Android SDK, Java JDK, and `adb` were entirely missing on the host.
  - Downloaded and configured OpenJDK 17 LTS (`C:\Users\kashy\AppData\Local\Android\jdk-17`).
  - Configured `JAVA_HOME`, `ANDROID_HOME`, and `ANDROID_SDK_ROOT` environment variables permanently.
  - Downloaded and installed `cmdline-tools` (v12.0) into `C:\Users\kashy\AppData\Local\Android\Sdk\cmdline-tools\latest`.
  - Installed `platform-tools` (with `adb.exe`) and added to user PATH.
  - Installed `platforms;android-36` and `build-tools;36.0.0`.
  - Accepted all Android SDK package licenses programmatically.
  - Verified with `flutter doctor -v`: Android toolchain is 100% verified and green (`[√] Android toolchain`).
- **Android Deployment Verification (2026-09-26)**:
  - Initial Gradle build failed due to missing `JAVA_HOME` in user subshell and unaccepted NDK/CMake/platform-35 licenses.
  - Automatically resolved all license agreements in `Android\Sdk\licenses`.
  - Downloaded NDK 28.2.13676358, CMake 3.22.1, and Android Platform 35.
  - Added `android.permission.INTERNET` to `AndroidManifest.xml`.
  - Added explicit scaffold background color to `GlassScaffold` in `karmi_shell.dart`.
  - Debug APK built successfully (`app-debug.apk` in 16.8s).
  - Detected connected physical device: **Pixel 9a** (`5B271XEBF3XDF0`).
  - Streamed install succeeded and launched `ai.karmi.karmi_app/.MainActivity`.
  - Verified live execution via logcat: Impeller Vulkan backend initialized and LiquidGlass library active.
- **Next Action**:
  - Download and bundle offline font files into `mobile/assets/google_fonts/`.
  - Proceed with Phase 5 verification and golden tests.

