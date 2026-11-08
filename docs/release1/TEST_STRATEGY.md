# Release 1 Test Strategy (Chat Redesign)

Owner: Manager-QAReleaseLead (squad H). Status: DRAFT v0.1, written from the baseline audit before `EXECUTION_CONTRACT.md` lands. Will be revised to match the contract's stream event, conversation and draft models.

## 1. Baseline (recorded 2026-10-21, branch `release1/chat-redesign`, pre-R1 code)

| Gate | Command | Result |
|---|---|---|
| Backend unit/model-lab/web | `make PYTHON=.venv/bin/python test-unit` | 166 passed, 1 DeprecationWarning (starlette/anyio) |
| Flutter static analysis | `cd mobile && flutter analyze` | No issues found |
| Flutter tests + goldens | `cd mobile && TZ=Asia/Kolkata flutter test` | 340 passed, 0 failed |
| Backend lint / typecheck / e2e | `make lint`, `make typecheck`, `make test-e2e` | See section 1.1 (filled from `/tmp/baseline_backend_rest.log`) |

Golden baselines: `mobile/test/goldens/linux/` (82 PNGs) and `mobile/test/goldens/windows/`. `golden_test.dart` renders chat, chat_empty, Armory tabs, welcome, plans, confirmation sheet, settings and glass legibility at light/dark x1.0/x2.0 and glass/opaque. Goldens are only compared on the host OS that generated them (linux here).

### 1.1 Backend lint/typecheck/e2e (baseline, pre-R1 code)
- `make PYTHON=.venv/bin/python lint`: exit 0, "All checks passed!", "secret scan: no matching credential material".
- `make PYTHON=.venv/bin/python typecheck`: exit 0, "Success: no issues found in 36 source files".
- `make PYTHON=.venv/bin/python test-e2e`: exit 0, "51 passed, 2 warnings in 5.31s".
- `make PYTHON=.venv/bin/python test-integration`: NOT run in baseline (needs docker/podman with disposable Postgres and Redis); must be run or recorded as unexecuted in QA_REPORT.

## 2. Current test surface (audit)

Backend (`tests/`, pytest config in `pyproject.toml`, `testpaths=["tests"]`, markers `integration`, `e2e`):
- `tests/unit/` (21 modules): gateway, gateway config, services, worker, ratelimit, security/Clerk, migrations, config, tier spelling, parakh bundle/actions, armory, opencode, readiness.
- `tests/e2e/` (7 modules): `test_api.py`, `test_api_remediation.py`, access codes, armory, feedback, gateway route, parakh exchange. Exercises the HTTP boundary via TestClient.
- `tests/integration/test_postgres_redis.py`: needs disposable Postgres and Redis (`make test-integration`, docker/podman).
- `tests/web/test_shell.py`: serves the web shell.
- `tests/model_lab/`: model lab core and opencode runner.

Gaps relevant to R1 (verified from source, not from docs):
- No conversation/chat model. `models.py` has `Run` (one per message) and `MessageFeedback`; no conversations, titles, pins, archives, drafts, or search tables. Persistence/search tests cannot exist until contract tables exist.
- No streaming endpoint. `POST /v1/messages` returns a full `MessageView` (`api.py`), `POST /v1/runs/{id}/regenerate` returns `MessageView`. Stream interruption/resume tests cannot exist until the stream contract lands.
- Mobile transport `mobile/lib/api/karmi_api.dart` uses `http.Client` with a 60 s timeout and no streaming body. Idempotency keys exist (`newIdempotencyKey`) and are reused on retry (see `chat_test.dart` offline case).

Mobile (`mobile/test/`, 16 Dart test files plus `golden_test.dart`):
- `features/chat_test.dart`: empty state, pending, reduced-motion pending, outcome chips, live-region announcements, 500 banner, offline retry with same idempotency key, 409 in-flight recheck, 429 limit and capacity messages, 401 sign-out, ASK_USER sheet.
- `features/chat_feedback_test.dart`: thumbs up/down, reason picker, regenerate replaces reply, feedback error with retry.
- `features/keyboard_focus_test.dart`, `features/device_regressions_test.dart`, `theme/glass_motion_test.dart`, `theme/karmi_colors_test.dart`, `widgets/prose_width_test.dart`, `api/karmi_api_test.dart`, `armory/armory_controller_test.dart`, `auth/clerk_sign_in_card_test.dart`, `fonts_test.dart`.
- Test support: `support/fake_backend.dart` (fake HTTP backend), `support/harness.dart`.
- `flutter_test_config.dart` disables runtime font fetching; any unbundled font fails the test.

## 3. Required new tests (R1 acceptance)

Each new test lives under `tests/` (Python) or `mobile/test/` (Dart). Test names must state the behaviour. A test must fail on the pre-R1 code where the behaviour is new.

### 3.1 Stream interruption and resume (backend `tests/unit` and `tests/e2e`; mobile `mobile/test/api` and `mobile/test/features`)
- Stream completes with a finish-reason; `finish_reason` is one of the contract's enumerated values. No stream ends silently without a terminal event.
- Heartbeat events are emitted at the contract interval during a slow provider call.
- Client disconnect mid-stream: the server persists the partial output and marks the run resumable; no duplicate charge (usage ledger row count unchanged on resume).
- Resume with `last_event_id`/offset returns only the missing suffix, stitched output equals the uninterrupted output.
- Stop cancels the run; Continue/Regenerate issue new runs with the contract's idempotency rules.
- Mobile: network drop mid-stream shows the categorized "interrupted, resumable" state, Resume uses the same idempotency key, duplicate text is not rendered.
- Batched UI updates: N deltas arriving in one frame produce at most one rebuild of the transcript (widget test counts rebuilds).

### 3.2 Persistence, search, rename/pin/archive/delete and Undo (backend `tests/unit` + `tests/e2e`; mobile `mobile/test/features`)
- Create chat; list ordered by pinned then last activity; pagination stable across pages.
- New Chat creates no DB row until the first user message is persisted (count assertion before and after).
- Search matches titles and message content; case-insensitive; results link to the message.
- Rename, pin, archive, unarchive: owner-scoped (other account gets 404, not 403 with data).
- Delete is soft with Undo window; Undo restores the chat and its messages; after the window the purge removes content. Migrations are additive only (`tests/unit/test_migrations.py` extended).
- Per-chat draft: text survives switching chats and an app restart (mobile widget test with a fake store).
- Integration (`make test-integration`, real Postgres): search index and ordering on real DB.

### 3.3 Composer paste and attachments (mobile `mobile/test/features`)
- Pasting text over the long-paste threshold inserts a chip, not raw text; the chip expands/removes; send submits the full text.
- Multiline: Shift+Enter inserts newline, Enter sends (keyboard support), IME composition does not send.
- Optimistic send: the user bubble appears before the response; on failure the text is restored into the composer.
- Attachment count and size limits enforced client-side with the server's error category.

### 3.4 Scroll behaviour (mobile `mobile/test/features`)
- New reply while at bottom keeps the end anchored.
- Scrolled up: new reply does not move the viewport; a "Jump to Latest" control appears with the unread count.
- Opening an old chat lands at the restored scroll position (or the end when none).
- Layout at tablet and phone widths (goldens) keeps the history rail visible/collapsed per contract.

### 3.5 Accessibility (mobile `mobile/test/features`, `mobile/test/theme`)
- Semantics: every icon button has a label; the streaming state announces transitions ("Assistant is writing response", "Response complete"), not per-token deltas.
- Reduced motion: no animation controllers run when `MediaQuery.disableAnimations` is true (assert with `tester.hasRunningAnimations == false`).
- Reduced transparency: glass surfaces resolve to opaque fills (golden `opaque` variant and unit assertion).
- Contrast: text tokens meet WCAG AA (4.5:1 body, 3:1 large/UI) for light and dark, computed by a Dart unit test over `karmi_colors`.
- Focus order and focus ring visible on keyboard navigation (existing `focus_ring.dart`).

### 3.6 Performance metrics (before/after; `docs/release1/perf/`)
- Backend: p50/p95 latency of `GET` chat list and search on a seeded dataset; time-to-first-byte of the stream endpoint.
- Mobile: cold-start to composer interactive (`flutter run --profile` or integration timing), frame build times during streaming (`flutter test` with `TimelineSummary` where available), transcript rebuild count per 100 deltas.
- Each metric recorded as before (pre-R1 commit `dcf4f75`) and after (release branch HEAD), with the command used, machine and date. No number is recorded without a command that reproduces it.

### 3.7 Golden updates
- Goldens are regenerated only by the QA squad with `flutter test --update-goldens` on linux, reviewed pixel diff by a human or auditor, and committed in a dedicated commit labelled `golden:`.
- New goldens required: history rail (tablet and phone), Jump to Latest, composer with paste chip, categorized error card, dark token patch, usage 80% warning.

## 4. Verification gates (final, run once after integration)

Backend (from `Makefile`/`scripts/tasks.py`):
1. `make PYTHON=.venv/bin/python lint` (ruff + secret scan)
2. `make PYTHON=.venv/bin/python typecheck` (mypy src)
3. `make PYTHON=.venv/bin/python test-unit`
4. `make PYTHON=.venv/bin/python test-e2e`
5. `make PYTHON=.venv/bin/python test-integration` (docker/podman required; record if unavailable and why)

Mobile (run in `mobile/`, IST):
1. `flutter analyze` (expect no issues)
2. `TZ=Asia/Kolkata flutter test` (all tests including goldens)

Every gate's command and key output lines (pass counts, exit codes) go into `QA_REPORT.md`.

## 5. Ownership

- QA squad H owns `tests/`, `mobile/test/` and `docs/release1/{TEST_STRATEGY,QA_REPORT}.md`, `docs/release1/perf/*`.
- Source changes needed to make tests pass are requested from Manager-IntegrationLead; QA does not edit `src/` or `mobile/lib/`.
- Independent auditor (explorer or reviewer worker, not the author of the change) reviews every risky workstream: stream protocol, persistence migrations, Undo/purge, auth-scoped search, and dark-mode tokens.

## 6. Release approval rules

- Reject if any required gate fails, any section-3 behaviour lacks a test, any golden diff is unreviewed, or a metric has no reproducing command.
- Reject if a migration is not additive, or if a production deploy/migration was attempted.
- Known-missing infrastructure (for example, Docker unavailable for integration) is recorded as an unexecuted gate, not as a pass.
