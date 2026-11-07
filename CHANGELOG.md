# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - unreleased (build 5)

### Added
- **Chat loading indicator**: Three-dot typing pulse (`KarmiTypingDots`) and placeholder shimmer (`KarmiSkeleton`) loading states for assistant responses (`mobile/lib/widgets/karmi_typing_dots.dart`, `mobile/lib/widgets/karmi_skeleton.dart`; commits `a23158b`, `5db031e`).
- **Google SSO onboarding integration**: "Continue with Google" sign-in via Clerk OAuth (`ai.karmi.app://sso-callback`) in onboarding flow (`account_auth_step.dart`, `google_sign_in_button.dart`; commits `4013244`, `d212da4`, `a7479ef`).
- **Deep link channel for Android**: MethodChannel (`ai.karmi.app/deep_links/messages`) and EventChannel (`ai.karmi.app/deep_links/events`) handling SSO redirect callbacks (`MainActivity.kt`, `AndroidManifest.xml`; commit `4013244`).
- **Customer bug reporting API**: Backend endpoint `POST /v1/bug-reports` with diagnostics allowlist, optional screenshot attachment (up to 5 MB), magic-byte validation, rolling 24-hour rate limiting, and idempotent replay (`src/daily_agent/routes/bug_reports.py`, `src/daily_agent/bug_reports_service.py`; commits `338a8c4`, `ac3d16e`).
- **Bug reports database schema**: Alembic migration `a5b6c7d8e9f0` creating the `bug_reports` table with status tracking, audit timestamps, and unique ticket allocation (`migrations/versions/a5b6c7d8e9f0_bug_reports.py`; commit `338a8c4`).
- **Mobile bug reporting UI & offline queue**: `BugReportScreen` accessible via Settings and Chat error cards with user consent toggle, diagnostics preview, `RepaintBoundary` screenshot capture, and resilient local queue serialization partitioned by user id (`mobile/lib/features/bug_report/`; commits `f6538d4`, `768598f`, `c799a27`).
- **Admin bug inbox API**: Endpoints `GET /v1/admin/bug-reports`, `GET /v1/admin/bug-reports/{id}`, `GET /v1/admin/bug-reports/{id}/screenshot`, and `PATCH /v1/admin/bug-reports/{id}` for status transitions and admin notes (`src/daily_agent/routes/admin.py`; commits `338a8c4`, `ac3d16e`).
- **Admin monitoring metrics**: Added `requests_today`, `daily_request_cap`, `success_rate`, `open_bug_reports`, `cost_today_inr`, and model-level latency and health table to `/v1/admin/monitor` (`src/daily_agent/admin_service.py`; commits `66c1535`, `ac3d16e`).
- **Mobile admin bug inbox**: Bug report list, detail view, and status update interface in mobile admin tooling (`mobile/lib/features/admin/`; commit `f6538d4`).
- **Persistent chat and streaming controls**: Resumable SSE streaming (`POST /v1/chat/stream`), Continue/Resume/Stop/Regenerate controls, multiline composer with text attachments, and conversation management (rename/pin/archive/delete with undo) (commits `a7b2025`, `cb16086`, `e472945`, `b0f0fdc`, `734e07b`).

### Changed
- **Unified shell layout**: Replaced divergent shell trees with a single layout tree unifying glass and solid/opaque modes with identical tab semantics (`mobile/lib/shell/karmi_shell.dart`; commits `66e0253`, `f6617d0`).
- **INR currency representation**: Cut over ledger representation and UI formatting from USD to Indian Rupees (INR) across plans, backend monitor, and mobile app; added `MICRO_PER_INR = 1_000_000`, `price_inr` plan prices, and Indian digit grouping formatter `formatInr` / `formatInrRupees` (`mobile/lib/widgets/money.dart`, `src/daily_agent/plans.py`; commits `66c1535`, `f6538d4`, `55a2bfe`).
- **Error card copy**: Streamlined chat error card copy to plain-words single sentence guidance with "Report this" entry point (`mobile/lib/features/chat/error_card.dart`; commits `3cbc0b0`, `f6617d0`).
- **Version bump**: Mobile client version incremented to `0.1.0+5` in `mobile/pubspec.yaml`.

### Fixed
- **Budget lock acquisition order**: Aligned settle and release lock order (`UsageWindow` -> `UsagePeriod` -> `PlatformBudget`) with reserve order to prevent deadlocks (port of PR #42; commit `ac83021`).
- **Empty failed reply action suppression**: Prevented message action buttons from displaying on empty failed assistant turns (`mobile/lib/features/chat/message_bubble.dart`; commits `1ca611e`, `5db031e`).
- **Jump pill dock clearance**: Ensured jump-to-latest button properly clears the composer dock across screen sizes (`mobile/lib/features/chat/jump_to_latest_pill.dart`; commits `bcd3967`, `f6617d0`).
- **Oversize screenshot handling**: Return HTTP 413 for payload size violations prior to pydantic 422 schema validation (`src/daily_agent/routes/bug_reports.py`; commit `22d3e8e`).
- **Diagnostics privacy leak prevention**: Omitted hostname and sanitized device model strings to avoid leaking PII in diagnostics payloads (`mobile/lib/features/bug_report/diagnostics_collector.dart`; commit `eeb7071`).
- **Sub-micro currency formatting**: Render non-zero sub-micro rupee amounts as `<₹0.01` (`mobile/lib/widgets/money.dart`; commit `b8bfc83`).
- **Admin CSP sources**: Permitted Clerk protect, image, worker, and challenge sources in `/admin` Content Security Policy (`src/daily_agent/web/admin_page.py`; commit `2a37177`).

### Security
- **Strict diagnostics allowlist**: Rejected unapproved client telemetry keys with HTTP 422 (`src/daily_agent/bug_reports_service.py`).
- **Screenshot magic byte validation**: Verified PNG/JPEG magic headers preventing binary payload MIME spoofing (`src/daily_agent/bug_reports_service.py`).
- **Admin session & route access**: Enforced Clerk token, admin allowlist, and `X-Admin-Session` header checks on all admin bug reporting endpoints.

### Known issues
- **Web admin UI**: web admin UI (overview tiles, bug inbox, screenshot viewer) NOT MERGED to 314afa4 — backend routes and CSP hardening only.
- **Device verification NOT VERIFIED (device testing paused by owner)**: Real device verification on Pixel 9a has not been executed; all device test checks remain paused.
- **R-9 golden visual review open**: Visual review by human owner for updated Flutter golden test assets remains pending.
- **Real Google sign-in NOT VERIFIED**: End-to-end Google OAuth sign-in against a live Clerk instance and real Google accounts has not been verified on physical devices (requires owner configuration in Clerk dashboard).
