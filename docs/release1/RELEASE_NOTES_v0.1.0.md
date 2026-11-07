# Karmi Release 1 — Release Notes (v0.1.0 Build 5)

**Version:** 0.1.0+5  
**Target Commit:** `314afa4` (branch `release1/final`)  
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
- **Payload Limits**: Max screenshot size enforced at 5 MB (5,242,880 bytes). Violations return HTTP 413 before Pydantic schema validation.
- **Content Validation**: Binary content-type checks require valid magic byte headers for `image/png` or `image/jpeg` (rejects with HTTP 415 on spoofing).
- **Diagnostics Allowlist**: Strict allowlist validation rejects unexpected telemetry fields with HTTP 422.
- **Rate Limiting & Idempotency**: Limited to 3 new reports per rolling 24 hours per user (HTTP 429 with `Retry-After`). Matching `client_report_id` with identical hash replays the existing record with HTTP 200; mismatched hash returns HTTP 409 conflict.

### Operator Monitoring & Admin Tooling
- **Metrics Endpoint `/v1/admin/monitor`**: Exposes `requests_today`, `daily_request_cap`, `success_rate`, `open_bug_reports`, `cost_today_inr`, and model-level latency and health (`model_health` table with p50 latency, run counts, error rate; never exposes prompts or secrets).
- **Admin Bug Inbox API**: Dedicated administrative endpoints (`GET /v1/admin/bug-reports`, `GET /v1/admin/bug-reports/{id}`, `GET /v1/admin/bug-reports/{id}/screenshot`, `PATCH /v1/admin/bug-reports/{id}`) requiring admin session authorization, audit logging, and mandatory transition reasons.
- **Web Admin UI Scope**: web admin UI (overview tiles, bug inbox, screenshot viewer) NOT MERGED to 314afa4 — backend routes and CSP hardening only.

---

## 3. Verification Status (Release Items 1–9)

| Item | Scope Description | Status | Reason & Evidence |
|---|---|---|---|
| Item 1 | Admin backend additions, monitoring metrics (`requests_today`, `open_bug_reports`, `cost_today_inr`, `model_health`), and streaming controls | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) (Backend) / Web UI NOT MERGED | Backend test files exist (`tests/unit/test_admin_bug_reports.py`, `tests/unit/test_admin_api.py`, `tests/e2e/test_admin_api.py`); not re-run for this commit. Web admin UI frontend is NOT MERGED to 314afa4. |
| Item 2 | Measured optimization (chat rebuilds ≤ 9, cached markdown, host timings, split-per-abi size reduction) | NOT VERIFIED | Optimization rework in progress on branch `r1f/perf` and not yet merged into `314afa4`. Host baselines recorded in `docs/release1/perf/BASELINE.md`; device timing is NOT VERIFIED (device testing paused by owner). |
| Item 3 | Loading motif & skeletons (`KarmiTypingDots`, `KarmiSkeleton`, no action buttons on empty failed turns) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Mobile unit and widget test files exist (`mobile/test/widgets/karmi_typing_dots_test.dart`, `mobile/test/widgets/karmi_skeleton_test.dart`; commit `5db031e`); not re-run for this commit. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 4 | Google Sign-in / SSO via Clerk OAuth (`ai.karmi.app://sso-callback`, "Continue with Google", deep link routing, account transfer) | PARTIALLY VERIFIED | Mobile widget and unit test files exist (`mobile/test/auth/google_sign_in_button_test.dart`, `mobile/test/auth/clerk_sso_test.dart`, `mobile/test/auth/account_auth_google_test.dart`); backend mapping test exists in `tests/e2e/test_clerk_sso_identity.py`; setup documented in `docs/release1/GOOGLE_SSO.md`; not re-run for this commit. Real Google sign-in is NOT VERIFIED (device testing paused by owner). |
| Item 5 | Money & INR representation (USD to INR renaming, `MICRO_PER_INR = 1_000_000`, `price_inr` plans, `formatInr`/`formatInrRupees`) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Unit test files exist in `mobile/test/widgets/money_test.dart` and `tests/unit/test_money.py`; plan test file exists in `tests/unit/test_plans.py` (commits `ac3d16e`, `6a5a7f2`); not re-run for this commit. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 6 | Bug reporting system (backend API `POST /v1/bug-reports`, migration `a5b6c7d8e9f0`, 5 MB cap, magic bytes, diagnostics allowlist, mobile UI, offline queue) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Backend test files exist (`tests/unit/test_bug_reports.py`, `tests/integration/test_bug_reports_pg.py`); mobile UI and queue test files exist (`mobile/test/features/bug_report/`, `mobile/test/features/chat/error_card_bug_report_test.dart`; commits `ac3d16e`, `6a5a7f2`); not re-run for this commit. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 7 | Unified shell layout (single layout tree for glass and solid modes, identical tab semantics) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Shell parity widget and golden test files exist (`mobile/test/shell/shell_parity_test.dart`; commit `f6617d0`); not re-run for this commit. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 8 | Error card copy rewrite & jump pill (plain-words single sentence error copy, jump-to-latest pill clearing composer dock) | EVIDENCE PRESENT (tests exist at 314afa4; gates not re-run by release-prep) | Widget test files exist in `mobile/test/features/chat/empty_state_test.dart` and `mobile/test/features/chat/jump_pill_test.dart` (commit `f6617d0`); not re-run for this commit. Physical device check is NOT VERIFIED (device testing paused by owner). |
| Item 9 | Web admin dashboard additions (backend routes and CSP configuration) | PARTIALLY VERIFIED | web admin UI (overview tiles, bug inbox, screenshot viewer) NOT MERGED to 314afa4 — backend routes and CSP hardening only. Backend test file exists in `tests/e2e/test_admin_api.py` and commit `2a37177`; not re-run for this commit. Browser/device runtime is NOT VERIFIED (device testing paused by owner). |
