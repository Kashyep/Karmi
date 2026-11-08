# Karmi Release 1 — Release Notes (v0.1.0 Build 5)

**Version:** 0.1.0+5  
**Target Commit:** Cut from `release1/final` HEAD at the time of the final gate run (exact SHA recorded in release sign-off)
**Date:** 2026-11-08  

---

## 1. User-Facing Notes

Karmi v0.1.0 (build 5) introduces the redesigned core chat surface, enhanced onboarding with Google Single Sign-On, native Indian Rupee (₹) pricing, and comprehensive in-app bug reporting.

### Core Chat & Shell Experience
- **Loading Indicators**: Assistant response generation is now marked by a three-dot typing pulse (`KarmiTypingDots`) and responsive skeleton shimmers (`KarmiSkeleton`), providing immediate visual feedback during streaming delays.
- **Unified Navigation Shell**: Merged glass and solid rendering modes into a single layout hierarchy, eliminating UI pop and layout shifts across themes.
- **Clear Error Communication**: Error cards have been rewritten into single-sentence, actionable plain language, including direct "Report this" links that pre-fill error diagnostic context.
- **Composer & Navigation Controls**: Stable end-anchored chat scrolling, a floating "Jump to Latest" pill that clears the composer dock, multiline composition, and offline-safe draft persistence.

### Account & Onboarding
- **Google Sign-In**: Added a "Continue with Google" sign-in option during onboarding via Clerk OAuth integration, supporting seamless deep link returns to the app (`ai.karmi.app://sso-callback`). Email code authentication remains fully supported as a fallback.
- **Transparent First-Run Notice**: Clear presentation of testing guidelines, tier entitlements, and privacy policies prior to account creation.

### Pricing & Indian Rupee (₹) Representation
- **Rupee-Native Display**: All subscription plans and credit values are displayed using Indian Rupee symbols (`₹`) and standard Indian numbering grouping (e.g. `₹1,49,900`, `₹0`, `<₹0.01`).
- **Dynamic Server Plans**: Tier names and plan prices are served dynamically from the backend (`price_inr`), ensuring client pricing consistency without hardcoded dollar signs.

### Customer Bug Reporting
- **In-App Issue Submission**: Users can report bugs directly from Settings or directly from any Chat error card.
- **Diagnostic Transparency**: Form displays all collected device diagnostics (OS version, app build, device model, locale, theme) before sending.
- **Optional Screenshots**: Users can opt in to attach a screenshot via a explicit consent toggle; screenshots are captured via a dedicated `RepaintBoundary` and exclude message text.
- **Offline Resilient Queue**: Bug reports are queued locally in encrypted storage and automatically retried when internet connectivity is restored. Each submission yields a unique ticket number (e.g., `KARMI-0001`).

---

## 2. Operator & Platform Notes

### Database Schema & Migrations
- **Migration `a5b6c7d8e9f0` (`bug_reports`)**: Creates the `bug_reports` table with schema `(id, account_id, user_id, ticket_number, client_report_id, request_hash, category, description, diagnostics, screenshot, screenshot_content_type, status, admin_notes, created_at, updated_at, triaged_at, resolved_at)`.
  - Reversible Alembic migration: `revision = "a5b6c7d8e9f0"`, `down_revision = "f4a5b6c7d8e9"`.
  - Concurrency-safe ticket numbering (`uq_bug_reports_ticket_number`) and replay deduplication (`uq_bug_reports_user_client_report_id`).

### Backend Financial & Ledger Contract
- **Currency Standard**: Removed all legacy `Settings.admin_micro_per_usd` configuration and aliases. Ledger unit is strictly micro-rupees (`INR_MICRO`, with `MICRO_PER_INR = 1_000_000`).
- **Payload & Field Cutover**: Endpoints and audit records utilize `price_inr`, `delta_inr`, `budget_inr`, `month_spend_inr`, and `spend_today_inr`.
- **Lock Ordering**: Fixed lock acquisition sequence in budget settlement and release operations (`UsageWindow` -> `UsagePeriod` -> `PlatformBudget`) to mirror reservation order and prevent concurrency deadlocks (port of PR #42).

### Bug Reporting API & Protection
- **Payload Limits & Body Limit (F-02)**: Max screenshot size enforced at 5 MB (5,242,880 bytes). Global request body size limit middleware enforced in `src/daily_agent/body_limit.py` returning HTTP 413 before Pydantic schema validation.
- **Content Validation**: Binary content-type checks require valid magic byte headers for `image/png` or `image/jpeg` (rejects with HTTP 415 on spoofing).
- **Diagnostics Allowlist**: Strict allowlist validation rejects unexpected telemetry fields with HTTP 422.
- **Rate Limiting & Idempotency Lock Order (F-03)**: Limited to 3 new reports per rolling 24 hours per user (HTTP 429 with `Retry-After`). Concurrency lock ordering in `src/daily_agent/bug_reports.py` ensures deterministic rate-limiting and replay checks. Matching `client_report_id` with identical hash replays the existing record with HTTP 200; mismatched hash returns HTTP 409 conflict.
### Operator Monitoring & Admin Tooling
- **Metrics Endpoint `/v1/admin/monitor`**: Exposes `requests_today`, `daily_request_cap`, `success_rate`, `open_bug_reports`, `cost_today_inr`, and model-level latency and health (`model_health` table with p50 latency, run counts, error rate; never exposes prompts or secrets).
- **Admin Bug Inbox API**: Dedicated administrative endpoints (`GET /v1/admin/bug-reports`, `GET /v1/admin/bug-reports/{id}`, `GET /v1/admin/bug-reports/{id}/screenshot`, `PATCH /v1/admin/bug-reports/{id}`) requiring admin session authorization, audit logging, and mandatory transition reasons.
- **Web Admin UI Scope**: Web admin UI is merged (commits `7f1f93d`, `818f6ad`). Includes overview metrics tiles, web bug inbox viewer, screenshot modal, and INR formatting in `admin.js`, gated by `DAILY_AGENT_ADMIN_UI_ENABLED`. Host tests pass; browser runtime verification is NOT VERIFIED (device testing paused by owner).

---

## 3. Verification Status (Release Items 1–9)

| Item | Scope Description | Status | Reason & Evidence |
|---|---|---|---|
| Item 1 | Admin backend additions, monitoring metrics (`requests_today`, `open_bug_reports`, `cost_today_inr`, `model_health`), and streaming controls | PARTIALLY VERIFIED | Web admin UI and backend are merged (commits `ac3d16e`, `64a70dc`, `e629d57`, `7f1f93d`, `818f6ad`). Backend and web test files exist (`tests/unit/test_admin_bug_reports.py`, `tests/unit/test_admin_api.py`, `tests/e2e/test_admin_api.py`, `tests/web/test_admin_page.py`, `tests/e2e/test_admin_bug_reports.py`); gates pending final run. Browser runtime and device testing: NOT VERIFIED (device testing paused by owner). |
| Item 2 | Measured optimization (chat rebuilds ≤ 9, cached markdown AST, host timings, split-per-abi size reduction) | PARTIALLY VERIFIED | Optimization merged in part: cached Markdown AST via `ParsedMarkdownCache` (`mobile/lib/features/chat/rendering/markdown_message.dart`), backend chat timing middleware default OFF via `DAILY_AGENT_CHAT_TIMING_ENABLED` (`src/daily_agent/chat_timing.py`; commit `47a15f2`). Composer ValueNotifier narrowing reverted with no measured reduction (`1a64e33`); no real rebuild reduction claimed; <=9 target met only by metric correction (corrected matcher base is 4; old 12 figure was an overcounting substring matcher); open client p95 ~+40 ms question unexplained, owner decision needed (documented in `docs/release1/perf/R1_FINAL.md`). Unit tests exist in `mobile/test/features/chat/rendering/markdown_message_test.dart` and `tests/unit/test_chat_timing.py`; gates pending final run. Device timing: NOT VERIFIED (device testing paused by owner). |
| Item 3 | Loading motif & skeletons (`KarmiTypingDots`, `KarmiSkeleton`, no action buttons on empty failed turns) | EVIDENCE PRESENT | Mobile unit and widget test files exist (`mobile/test/widgets/karmi_typing_dots_test.dart`, `mobile/test/widgets/karmi_skeleton_test.dart`; commits `5db031e`, `ec578d6`); gates pending final run. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 4 | Google Sign-in / SSO via Clerk OAuth (`ai.karmi.app://sso-callback`, "Continue with Google", deep link routing, account transfer) | PARTIALLY VERIFIED | Mobile widget and unit test files exist (`mobile/test/auth/google_sign_in_button_test.dart`, `mobile/test/auth/clerk_sso_test.dart`, `mobile/test/auth/account_auth_google_test.dart`); backend mapping test exists in `tests/e2e/test_clerk_sso_identity.py` (commits `a7479ef`, `65a79a2`; documented in `docs/release1/GOOGLE_SSO.md`); gates pending final run. Real Google sign-in is NOT VERIFIED; owner step remains (enable Clerk Google SSO on dev instance and add redirect allowlist `ai.karmi.app://sso-callback`). Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 5 | Money & INR representation (USD to INR renaming, `MICRO_PER_INR = 1_000_000`, `price_inr` plans, `formatInr`/`formatInrRupees`) | EVIDENCE PRESENT | Unit test files exist in `mobile/test/widgets/money_test.dart`, `tests/unit/test_money.py`, and `tests/unit/test_plans.py` (commits `ac3d16e`, `6a5a7f2`, `b8bfc83`, `55a2bfe`, `9cf2ce4` [F5 NaN/Inf guard]); gates pending final run. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 6 | Bug reporting system (backend API `POST /v1/bug-reports`, migration `a5b6c7d8e9f0`, 5 MB cap, magic bytes, diagnostics allowlist, mobile UI, offline queue, F-02 body limit, F-03 lock order) | EVIDENCE PRESENT | Backend migration `migrations/versions/a5b6c7d8e9f0_bug_reports.py`, backend test files `tests/unit/test_bug_reports.py`, `tests/integration/test_bug_reports_pg.py`, `tests/e2e/test_bug_report_body_limit.py`, `tests/e2e/test_bug_reports.py`, mobile UI and queue test files `mobile/test/features/bug_report/`, `mobile/test/features/chat/error_card_bug_report_test.dart` (commits `ac3d16e`, `6a5a7f2`, `74b63cc` [F-02 body limit in `src/daily_agent/body_limit.py`, F-03 lock order], `9cf2ce4` [F4 dead alias removed, owner fail-closed]); gates pending final run. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 7 | Unified shell layout (single layout tree for glass and solid modes, identical tab semantics) | EVIDENCE PRESENT | Shell parity widget and golden test files exist (`mobile/test/shell/shell_parity_test.dart`; commits `f6617d0`, `66e0253`); gates pending final run. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 8 | Error card copy rewrite & jump pill (plain-words single sentence error copy, jump-to-latest pill clearing composer dock) | EVIDENCE PRESENT | Widget test files exist in `mobile/test/features/chat/empty_state_test.dart` and `mobile/test/features/chat/jump_pill_test.dart` (commits `f6617d0`, `3cbc0b0`, `bcd3967`, `c322f17`); gates pending final run. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 9 | Web admin dashboard additions (backend routes, overview tiles, bug inbox, screenshot viewer, and CSP configuration) | PARTIALLY VERIFIED | Web admin UI is merged (commits `7f1f93d`, `818f6ad`). Static assets `admin.js`, `admin.css`, and templates in `src/daily_agent/web/` verified in repo. Tests exist: `tests/web/test_admin_page.py`, `tests/e2e/test_admin_api.py`, `tests/e2e/test_admin_bug_reports.py` (including F-08 filter validation and CSP style-src config); gates pending final run. Browser runtime and device testing: NOT VERIFIED (device testing paused by owner). |
