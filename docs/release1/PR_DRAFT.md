# Release 1 final: 0.1.0+5

> **Status:** Draft — do not open until owner approval  
> **Source branch:** `release1/final` (`314afa4`)  
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
- **Admin Content Security Policy Hardening & Web Admin Scope (`2a37177`)**:
  - web admin UI (overview tiles, bug inbox, screenshot viewer) NOT MERGED to 314afa4 — backend routes and CSP hardening only.
  - Configured CSP in `/admin` to permit Clerk protect, image, worker, and challenge sources (`2a37177`).
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
- **Test Suite Determinism (`314afa4`)**:
  - Pinned clock in conversation grouping tests to eliminate midnight timezone flaking (`314afa4`).

---

## Verification status

| Item | Scope Description | Status | Evidence |
|---|---|---|---|
| **Item 1** | Admin backend additions, monitoring metrics (`requests_today`, `open_bug_reports`, `cost_today_inr`, `model_health`), and streaming controls | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) (Backend) / Web UI NOT MERGED | Backend test files exist: `tests/unit/test_admin_bug_reports.py`, `tests/unit/test_admin_api.py`, `tests/e2e/test_admin_api.py` (commits `ac3d16e`, `64a70dc`, `e629d57`); not re-run for this commit. Web admin frontend is pending integration (see `## RECONCILE (supervisor)`). Device/browser: NOT VERIFIED (device testing paused by owner). |
| **Item 2** | Measured optimization (chat rebuilds ≤ 9, cached markdown AST, host timings, split-per-abi size reduction) | NOT VERIFIED | Optimization rework remains in progress on branch `r1f/perf` and is NOT MERGED into `314afa4`. Host baseline documented in `docs/release1/perf/BASELINE.md`. Device timing: NOT VERIFIED (device testing paused by owner). |
| **Item 3** | Loading motif & skeletons (`KarmiTypingDots`, `KarmiSkeleton`, no actions on empty failed turn) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Mobile unit and widget test files exist: `mobile/test/widgets/karmi_typing_dots_test.dart`, `mobile/test/widgets/karmi_skeleton_test.dart` (commit `5db031e`, `ec578d6`); not re-run for this commit. Device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 4** | Google Sign-in / SSO via Clerk OAuth (`ai.karmi.app://sso-callback`, "Continue with Google", deep link routing, account transfer) | PARTIALLY VERIFIED | Mobile widget and unit test files exist: `mobile/test/auth/google_sign_in_button_test.dart`, `mobile/test/auth/clerk_sso_test.dart`, `mobile/test/auth/account_auth_google_test.dart`; backend mapping test exists: `tests/e2e/test_clerk_sso_identity.py` (commits `a7479ef`, `65a79a2`; documented in `docs/release1/GOOGLE_SSO.md`); not re-run for this commit. Real Google sign-in and device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 5** | Money & INR representation (USD to INR renaming, `MICRO_PER_INR = 1_000_000`, `price_inr` plans, `formatInr`/`formatInrRupees`) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Unit test files exist: `mobile/test/widgets/money_test.dart`, `tests/unit/test_money.py`, `tests/unit/test_plans.py` (commits `ac3d16e`, `6a5a7f2`, `b8bfc83`, `55a2bfe`); not re-run for this commit. Device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 6** | Bug reporting system (backend API `POST /v1/bug-reports`, migration `a5b6c7d8e9f0`, 5 MB cap, magic bytes, diagnostics allowlist, mobile UI, offline queue) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Backend migration `migrations/versions/a5b6c7d8e9f0_bug_reports.py`, backend test files `tests/unit/test_bug_reports.py`, `tests/integration/test_bug_reports_pg.py`, mobile UI and queue test files `mobile/test/features/bug_report/`, `mobile/test/features/chat/error_card_bug_report_test.dart` (commits `ac3d16e`, `6a5a7f2`); not re-run for this commit. Device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 7** | Unified shell layout (single layout tree for glass and solid modes, identical tab semantics) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Shell parity widget and golden test files exist: `mobile/test/shell/shell_parity_test.dart` (commit `f6617d0`, `66e0253`); not re-run for this commit. Device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 8** | Error card copy rewrite & jump pill (plain-words single sentence error copy, jump-to-latest pill clearing composer dock) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Widget test files exist: `mobile/test/features/chat/empty_state_test.dart`, `mobile/test/features/chat/jump_pill_test.dart` (commit `f6617d0`, `3cbc0b0`, `bcd3967`, `c322f17`); not re-run for this commit. Device testing: NOT VERIFIED (device testing paused by owner). |
| **Item 9** | Web admin dashboard additions (backend routes and CSP configuration) | PARTIALLY VERIFIED | web admin UI (overview tiles, bug inbox, screenshot viewer) NOT MERGED to 314afa4 — backend routes and CSP hardening only. Backend test file exists: `tests/e2e/test_admin_api.py` (commit `2a37177`); not re-run for this commit. Device and browser testing: NOT VERIFIED (device testing paused by owner). |

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

## RECONCILE (supervisor)

- Branch `r1f/webadmin` (last commit `cfd2932` `fix(lint): suppress ruff S607 on node check in generate_screenshots.py`): Web admin dashboard additions (INR formatting in `admin.js`, overview metrics tiles, web bug inbox viewer, Playwright screenshots at 360px and 1440px, and `DAILY_AGENT_ADMIN_UI_ENABLED` gate) — `NOT MERGED`.
- Branch `r1f/perf` (last commit `56629c2` `perf(backend): A/B benchmark compare mode and direct middleware overhead measurement`): Item 2 measured optimization (composer rebuild scope narrowing, cached Markdown AST, backend latency compare mode and timing logs, and split-per-abi APK size measurements) — `NOT MERGED`.
- Branch `r1f/release` (last commit `256a6e9` `docs(release): add changelog, release notes, sha256 and signing recipe`): Release documentation and version bump branch (version bump to 0.1.0+5, changelog, release notes, SHA256SUMS recipe, owner runbook, PR draft, and Memory updates) — `NOT MERGED`.
