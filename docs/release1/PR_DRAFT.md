# Release 1 final: 0.1.0+5

> **Status:** Draft — do not open until owner approval  
> **Source branch:** `release1/final` (cut from `release1/final` HEAD at the time of the final gate run; exact SHA recorded in release sign-off)  
> **Target branch:** `main`  
> **Version:** `0.1.0+5` (`mobile/pubspec.yaml`)  
> **Date:** 2026-11-08  

---

## Summary

This pull request integrates Karmi Release 1 (`release1/final` at commit `314afa4`) into `main`.

*Note on release tag comparison:* The tag `v0.1.0+4` is not present in repository git tags (`git tag -l` reports only `v0.1.0-beta.1`). Per repository release records in `Memory.md`, build `v0.1.0+4` corresponds to commit `b9a4457` (2026-10-24). The 58 commits between `b9a4457` and `314afa4` (`git log --oneline b9a4457..314afa4`) comprise the following changes:

- **Chat Redesign & Core Experience (`734e07b`)**:
  - Full chat surface redesign incorporating resumable streaming, local conversation history, search/rename/pin/archive/delete with undo, and multiline composer (`734e07b`, `df0a507`).
- **Loading Indicators & Turn Handling (Wave 3, `5db031e`)**:
  - Added `KarmiTypingDots` pulse and `KarmiSkeleton` placeholders for streaming response states (`a23158b`, `ec578d6`).
  - Suppressed action buttons on empty failed assistant turns (`1ca611e`, `afc9685`, `f4346ad`).
- **Unified Navigation Shell & Error Card Rewrites (Wave 1, `f6617d0`)**:
  - Unified glass and solid rendering modes into a single layout hierarchy to eliminate visual shifts across themes (`66e0253`).
  - Rewrote error cards into plain-words, single-sentence copy (`3cbc0b0`, `c322f17`).
  - Added jump-to-latest pill that clears the composer dock (`bcd3967`).
- **Web Admin Dashboard & Admin CSP Hardening (`2a37177`, `7f1f93d`, `818f6ad`)**:
  - Web admin UI merged in `7f1f93d`: includes overview metrics tiles, web bug inbox viewer, screenshot modal, and INR formatting in `src/daily_agent/web/static/admin.js`, gated by `DAILY_AGENT_ADMIN_UI_ENABLED`.
  - Configured CSP in `/admin` to permit Clerk protect, image, worker, and challenge sources (`2a37177`), with `style-src 'unsafe-inline'` when Clerk is configured (`fd546f4`, `818f6ad`).
  - Added filter validation returning 422 on unknown bug-report status or category (`0654f19`, `818f6ad`).
- **Backend Ledger, Currency Standard & Concurrency (Wave 2, `ac3d16e`)**:
  - Ported PR #42 lock acquisition ordering (`UsageWindow` -> `UsagePeriod` -> `PlatformBudget`) in settlement and release operations to prevent deadlocks (`ac83021`, `5f6eb0b`).
  - Created reversible migration `a5b6c7d8e9f0` adding the `bug_reports` table with unique ticket indexing (`338a8c4`).
  - Removed legacy USD aliases (`Settings.admin_micro_per_usd`), established `MICRO_PER_INR = 1_000_000`, added dynamic server plan pricing (`price_inr`), and added `/v1/admin/monitor` operational metrics (`66c1535`, `64a70dc`, `e629d57`).
  - Added customer bug report API (`POST /v1/bug-reports`, `GET /v1/bug-reports/{id}`) and admin endpoints (`GET /v1/admin/bug-reports`, detail, screenshot, and status `PATCH`) with 5 MB screenshot limit returning HTTP 413, magic-byte format validation returning HTTP 415, diagnostics allowlist returning HTTP 422, rate limiting (3/24h) returning HTTP 429, and concurrency-safe ticket allocation (`22d3e8e`, `a10ef22`, `b244488`, `8c93d13`).
- **Mobile Application Bug Reporting, Rupee Pricing & Settings (Wave 5, `6a5a7f2`, `a86a206`, `a7d2cb7`)**:
  - Implemented `formatInr` and `formatInrRupees` helpers supporting Indian digit grouping, whole-rupee suppression of decimals, and `<₹0.01` formatting (`b8bfc83`, `55a2bfe`).
  - Removed hardcoded dollar strings in plans and onboarding, consuming dynamic `price_inr` values (`f6538d4`).
  - Built customer bug report flow in Settings and Chat error cards ("Report this") with diagnostics disclosure excluding hostnames/PII, optional screenshot toggle using `RepaintBoundary`, and offline encrypted queue with replay and retry logic (`f6538d4`, `768598f`, `c799a27`, `08a9505`, `51081db`, `06bc02a`, `eeb7071`, `b089b81`, `11be2b7`, `24b091d`).
  - Integrated bug inbox list, detail, and status updates with reason in mobile Admin tooling (`f6538d4`, `93f74e0`).
- **Google Sign-In via Clerk OAuth (Wave 6, `a7479ef`, `65a79a2`)**:
  - Added branded "Continue with Google" sign-in button in onboarding following Google design guidelines (`4013244`, `1167e10`, `5284356`).
  - Configured Clerk OAuth deep link callback handler for `ai.karmi.app://sso-callback` (`1f0630f`, `d212da4`).
  - Handled OAuth sign-in to sign-up user transfer, cancellation messages, and error states (`42cc4ca`, `550abf6`, `832eb6a`, `5875f2d`).
  - Added backend E2E test file `tests/e2e/test_clerk_sso_identity.py` covering Clerk `sub` identity mapping to existing users and new customer provisioning (`035ff3c`).
  - Documented setup and owner checklist in `docs/release1/GOOGLE_SSO.md` (`2931b2c`).
- **Performance Rework & AST Caching (`47a15f2`)**:
  - Parsed Markdown AST cache in `markdown_message.dart` (`01db879`).
  - Composer ValueNotifier narrowing reverted (`1a64e33`) after measuring no rebuild reduction (+2 on pre-revert branch; composer behaviorally matches base).
  - Chat timing middleware added with default OFF via `DAILY_AGENT_CHAT_TIMING_ENABLED` (`2cc5ad7`); benchmarking scripts and honest perf evaluation recorded in `docs/release1/perf/R1_FINAL.md`.
- **Backend Fixes & Hardening (`74b63cc`, `818f6ad`, `9cf2ce4`)**:
  - Added request body size limit enforcement middleware (`src/daily_agent/body_limit.py`, F-02).
  - Bug report lock acquisition ordering and concurrency safety (`src/daily_agent/bug_reports.py`, F-03).
  - Admin bug-report filter validation returning 422 on unknown status/category (`src/daily_agent/routes/admin.py`, F-08).
  - Currency helper guard in `formatInrRupees` returning ₹0 on NaN/Infinity (`mobile/lib/widgets/money.dart`, F5).
  - Bug report owner identity evaluated fail-closed on session change (`mobile/lib/features/bug_report/bug_report_screen.dart`).
- **Test Suite Determinism (`314afa4`)**:
  - Pinned clock in conversation grouping tests to eliminate midnight timezone flaking (`314afa4`).

---

## Verification status

| Item | Scope Description | Status | Evidence |
|---|---|---|---|
| **Item 1** | Admin backend additions, monitoring metrics (`requests_today`, `open_bug_reports`, `cost_today_inr`, `model_health`), and streaming controls | PARTIALLY VERIFIED | Web admin UI and backend are merged (commits `ac3d16e`, `64a70dc`, `e629d57`, `7f1f93d`, `818f6ad`). Backend and web test files exist: `tests/unit/test_admin_bug_reports.py`, `tests/unit/test_admin_api.py`, `tests/e2e/test_admin_api.py`, `tests/web/test_admin_page.py`, `tests/e2e/test_admin_bug_reports.py`; gates pending final run. Browser verification and device runtime: NOT VERIFIED (device testing paused by owner; browser runtime verification not executed on live environment). |
| **Item 2** | Measured optimization (chat rebuilds ≤ 9, cached markdown AST, host timings, split-per-abi size reduction) | PARTIALLY VERIFIED | Optimization merged in part: cached Markdown AST via `ParsedMarkdownCache` (`mobile/lib/features/chat/rendering/markdown_message.dart`), backend chat timing middleware default OFF via `DAILY_AGENT_CHAT_TIMING_ENABLED` (`src/daily_agent/chat_timing.py`; commit `47a15f2`). Composer ValueNotifier narrowing reverted with no measured reduction (`1a64e33`); no real rebuild reduction claimed; <=9 target met only by metric correction (corrected matcher base is 4; old 12 figure was an overcounting substring matcher); open client p95 ~+40 ms question unexplained, owner decision needed (documented in `docs/release1/perf/R1_FINAL.md`). Unit tests exist in `mobile/test/features/chat/rendering/markdown_message_test.dart` and `tests/unit/test_chat_timing.py`; gates pending final run. Device timing: NOT VERIFIED (device testing paused by owner). |
| **Item 3** | Loading motif & skeletons (`KarmiTypingDots`, `KarmiSkeleton`, no actions on empty failed turn) | EVIDENCE PRESENT | Mobile unit and widget test files exist: `mobile/test/widgets/karmi_typing_dots_test.dart`, `mobile/test/widgets/karmi_skeleton_test.dart` (commits `5db031e`, `ec578d6`); gates pending final run. Physical device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 4** | Google Sign-in / SSO via Clerk OAuth (`ai.karmi.app://sso-callback`, "Continue with Google", deep link routing, account transfer) | PARTIALLY VERIFIED | Mobile widget and unit test files exist: `mobile/test/auth/google_sign_in_button_test.dart`, `mobile/test/auth/clerk_sso_test.dart`, `mobile/test/auth/account_auth_google_test.dart`; backend mapping test exists: `tests/e2e/test_clerk_sso_identity.py` (commits `a7479ef`, `65a79a2`; documented in `docs/release1/GOOGLE_SSO.md`); gates pending final run. Real Google sign-in: NOT VERIFIED; owner step remains (enable Clerk Google SSO on dev instance and add redirect allowlist `ai.karmi.app://sso-callback`). Physical device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 5** | Money & INR representation (USD to INR renaming, `MICRO_PER_INR = 1_000_000`, `price_inr` plans, `formatInr`/`formatInrRupees`) | EVIDENCE PRESENT | Unit test files exist: `mobile/test/widgets/money_test.dart`, `tests/unit/test_money.py`, `tests/unit/test_plans.py` (commits `ac3d16e`, `6a5a7f2`, `b8bfc83`, `55a2bfe`, `9cf2ce4` [F5 NaN/Inf guard]); gates pending final run. Physical device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 6** | Bug reporting system (backend API `POST /v1/bug-reports`, migration `a5b6c7d8e9f0`, 5 MB cap, magic bytes, diagnostics allowlist, mobile UI, offline queue, F-02 body limit, F-03 lock order) | EVIDENCE PRESENT | Backend migration `migrations/versions/a5b6c7d8e9f0_bug_reports.py`, backend test files `tests/unit/test_bug_reports.py`, `tests/integration/test_bug_reports_pg.py`, `tests/e2e/test_bug_report_body_limit.py`, `tests/e2e/test_bug_reports.py`, mobile UI and queue test files `mobile/test/features/bug_report/`, `mobile/test/features/chat/error_card_bug_report_test.dart` (commits `ac3d16e`, `6a5a7f2`, `74b63cc` [F-02 body limit in `src/daily_agent/body_limit.py`, F-03 idempotency/rate-limit lock], `9cf2ce4` [F4 dead alias removed, owner fail-closed]); gates pending final run. Physical device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 7** | Unified shell layout (single layout tree for glass and solid modes, identical tab semantics) | EVIDENCE PRESENT | Shell parity widget and golden test files exist: `mobile/test/shell/shell_parity_test.dart` (commits `f6617d0`, `66e0253`); gates pending final run. Physical device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 8** | Error card copy rewrite & jump pill (plain-words single sentence error copy, jump-to-latest pill clearing composer dock) | EVIDENCE PRESENT | Widget test files exist: `mobile/test/features/chat/empty_state_test.dart`, `mobile/test/features/chat/jump_pill_test.dart` (commits `f6617d0`, `3cbc0b0`, `bcd3967`, `c322f17`); gates pending final run. Physical device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 9** | Web admin dashboard additions (backend routes, overview tiles, bug inbox, screenshot viewer, and CSP configuration) | PARTIALLY VERIFIED | Web admin UI is merged (commits `7f1f93d`, `818f6ad`). Static assets `admin.js`, `admin.css`, and templates in `src/daily_agent/web/` verified in repo. Tests exist: `tests/web/test_admin_page.py`, `tests/e2e/test_admin_api.py`, `tests/e2e/test_admin_bug_reports.py` (including F-08 filter validation and CSP style-src config); gates pending final run. Browser runtime and device testing: NOT VERIFIED (device testing paused by owner; browser runtime verification not executed on live environment). |

### Historical Gate Results

- **2026-10-22 at `4b95f5c`** (cited from `docs/release1/RELEASE_REPORT.md` §4 and `docs/release1/QA_REPORT.md`):
  - Backend lint & secret scan: clean (exit 0)
  - Backend typecheck: clean across 49 files (exit 0)
  - Backend unit tests: 226 passed (exit 0)
  - Backend E2E tests: 62 passed (exit 0)
  - Backend integration tests: 6 passed (exit 0)
  - Flutter analyze: clean (exit 0)
  - Flutter a11y & chat suites: 103 passed
- **Commit `314afa4`**: not re-run for this commit by the release-prep agent.

---

## Known risks

1. **R-9 Open (Visual Review of Goldens)**: Regenerated Linux goldens across chat, empty states, and shell parity have not undergone visual sign-off by a human reviewer.
2. **Real Google Sign-In NOT VERIFIED**: End-to-end Google OAuth on a live Clerk instance with production credentials has not been executed. Dashboard configuration and callback allowlisting remain required owner actions.
3. **Device Behaviour NOT VERIFIED**: Physical device testing on the reference hardware (Pixel 9a) was paused by owner directive. Cold start timing, touch gesture responsiveness, live frame rates, TalkBack swipe interactions, and runtime memory consumption on hardware are not verified.

---

## Test plan

Reviewers should execute the test commands defined in the repository:

### Backend Checks
```bash
# Defined in scripts/tasks.py (lines 169-179) and .github/workflows/ci.yml (lines 24-35)
python scripts/tasks.py lint
python scripts/tasks.py typecheck
python scripts/tasks.py test-unit
python scripts/tasks.py test-e2e
python scripts/tasks.py test-integration
```

### Mobile Checks
```bash
# Defined in local://r1-contract.md (lines 17-20) and .github/workflows/ci.yml (lines 53-64)
cd mobile
flutter pub get
dart format --output=none --set-exit-if-changed .
flutter analyze
TZ=Asia/Kolkata flutter test --reporter=failures-only
```

### Release Build Check
```bash
# Defined in docs/release1/SHA256_AND_SIGNING.md (lines 14-22)
cd mobile
flutter build apk --release --split-per-abi
```

---

## Migration notice

- **Revision:** `a5b6c7d8e9f0` (`bug_reports` table)
- **Source file:** `migrations/versions/a5b6c7d8e9f0_bug_reports.py`
- **Reversibility:** Fully reversible via `downgrade()` (drops table `bug_reports`).
- **`down_revision`:** `"f4a5b6c7d8e9"` (verified from `migrations/versions/a5b6c7d8e9f0_bug_reports.py` line 14).
- **Deployment & execution notice:** Database migration and backend deployment are NOT executed by this pull request. Reviewers and operators must refer to `docs/release1/OWNER_STEPS.md` for backup procedures, upgrade sequence, verification, and rollback runbooks.

---

## RECONCILED (supervisor)

All release branches have been merged into `release1/final`:

- Branch `r1f/webadmin`: Merged at commit `7f1f93d` (`merge: r1f/webadmin (W4 web admin: INR, bug inbox, security rework) into release1/final`). Status: MERGED. Web admin dashboard additions (INR formatting in `admin.js`, overview metrics tiles, web bug inbox viewer, Playwright screenshots at 360px and 1440px, and `DAILY_AGENT_ADMIN_UI_ENABLED` gate).
- Branch `r1f/fix`: Merged at commit `74b63cc` (`merge: r1f/fix (body-limit F-02, bug-report lock order F-03) into release1/final`). Status: MERGED. Request body size limit middleware in `src/daily_agent/body_limit.py` (F-02) and bug report concurrency lock ordering in `src/daily_agent/bug_reports.py` (F-03).
- Branch `r1f/perf`: Merged at commit `47a15f2` (`merge: r1f/perf (reverted composer narrowing, Markdown cache, honest perf report, timing default OFF) into release1/final`). Status: MERGED. Item 2 measured optimization: composer ValueNotifier narrowing reverted (`1a64e33`) with no measured reduction, cached Markdown AST kept in `markdown_message.dart`, backend chat timing middleware added with default OFF via `DAILY_AGENT_CHAT_TIMING_ENABLED`, honest perf report in `docs/release1/perf/R1_FINAL.md`.
- Branch `r1f/p3-app`: Merged at commit `9cf2ce4` (`merge: r1f/p3-app (dead alias F4, NaN/Inf money guard F5, owner fail-closed F-bug-report)`). Status: MERGED. P3 mobile app fixes: dead alias F4 removed, `formatInrRupees` returns ₹0 for NaN/Infinity (F5), bug-report owner fail-closed on session change.
- Branch `r1f/p3-backend`: Merged at commit `818f6ad` (`merge: r1f/p3-backend (admin filter 422 F-08, Clerk style-src, access-log runbook F-05)`). Status: MERGED. P3 backend fixes: admin bug-report filter validation returning 422 on unknown (F-08), admin CSP `style-src 'unsafe-inline'` when Clerk is configured, access-log redaction runbook section (F-05).
- Branch `r1f/release`: Merged at commit `fedf535` (`merge: r1f/release (changelog, release notes, 0.1.0+5, PR draft, owner runbook)`). Status: MERGED. Release documentation and version bump branch (version bump to 0.1.0+5 in `mobile/pubspec.yaml`, changelog, release notes, SHA256SUMS recipe, owner runbook, PR draft, and Memory updates).
