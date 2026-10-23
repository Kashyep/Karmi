# Karmi Release 1 (chat redesign): Release Report

Status: Final for release-candidate review. Verdict and sign-off are in `docs/release1/QA_REPORT.md` (updated after R1 rejection round 1).
Branch: `release1/chat-redesign`, HEAD `4b95f5c`. Base: `origin/main` `dcf4f75`.
Machine: linux 7.2.11-arch1-1, x64. Flutter 3.47.5 (stable), per `docs/release1/perf/BASELINE.md`.

Evidence rule: every number is either quoted from a named handoff or document, or was re-run for this report on 2026-10-22 at HEAD `4b95f5c` (marked "re-run"). Anything not measured is marked NOT MEASURED.

## 1. Governing documents

| Document | Path |
|---|---|
| Execution contract (v1, `5de20a8`) | `docs/release1/EXECUTION_CONTRACT.md` |
| Dependency board | `docs/release1/DEPENDENCY_BOARD.md` |
| Scope and timeline | `docs/release1/SCOPE_TIMELINE.md` |
| Test strategy | `docs/release1/TEST_STRATEGY.md` |
| Squad handoffs | `docs/release1/handoffs/{A,B,BW,C,D,E,F,G,QA1,FIX,WIRING}.md` |
| Backend QA audit (10 findings, all fixed) | `docs/release1/QA_AUDIT_BACKEND.md` |
| Client QA audit (5 findings, all fixed) | `docs/release1/QA_AUDIT_CLIENT.md` |
| Accessibility QA | `docs/release1/QA_A11Y.md` |
| QA report and verdict | `docs/release1/QA_REPORT.md` |
| Perf | `docs/release1/perf/BASELINE.md`, `docs/release1/perf/AFTER.md`, `docs/release1/perf/AFTER_STARTUP.md`, `docs/release1/perf/BASELINE_TEST_TIMINGS.md`, `docs/release1/perf/measure.sh` |
| R1.1 backlog (NOT in R1 scope) | `docs/release1/R1_1_BACKLOG.md` |

## 2. Scope: R1 items and evidence

The plan's R1 scope is recorded in `SCOPE_TIMELINE.md` as R1-1 to R1-7. R1-7 bundles performance with the token, usage-pill and a11y work; it is split below into 7a (performance) and 7b (tokens, usage pill, a11y) so that the eight items are each traceable. The split is this report's mapping, not a change to the scope.

| # | R1 item | Squad / commits | Evidence | Status |
|---|---|---|---|---|
| 1 | R1-1 Complete, resumable streaming; Continue, Resume, Stop, Regenerate; heartbeats; finish reason; typed events | A: `e472945`, `4f785fc`, `e0dbbb1`; BW: `365e17f`, `938b060`; FIX: `59d4609`, `4b5ccb3` | `handoffs/A.md`, `handoffs/BW.md`, `handoffs/FIX.md`, contract §2 | Implemented. Resume is process-lifetime only (D5). Provider streaming mode for OpenCode NOT VERIFIED (D4). |
| 2 | R1-2 Persistent chats: history, search, rename, pin, archive, delete with Undo, drafts; New Chat creates no empty record | B: `cb16086`, `f41d011`; drafts in E: `7b2d17e`; Postgres tests: `8eb0f81` | `handoffs/B.md`, `handoffs/QA1.md`, `tests/integration/test_conversations_pg.py` | Implemented. Search is substring only (D7). Drafts are device-local (D3). |
| 3 | R1-3 Responsive workspace; stable end-anchored scroll; Jump to Latest; history rail; tablet and mobile layouts | C: `a2bf8e2`, `cd7a5ec`, `f2aabf6`; history rail wiring: `5a295ea`; AUDIT-04 fix: `4b95f5c` | `handoffs/C.md` (10 scroll tests, 11 shell tests); `mobile/test/qa/scroll_screen_test.dart` | Implemented. Medium and expanded layouts verified by widget tests at 400, 800 and 1200 widths only (no device). |
| 4 | R1-4 Safe rich rendering: markdown, code (copy, language, wrap), tables, files, citations, long-output folding | D: `d17831e`, `dddb9d5` | `handoffs/D.md` (8 widget tests), golden `mobile/test/features/chat/rendering/goldens/markdown_message_basic.png` | Implemented. Artifact and Sources drawers deferred to R1.1-5 (R-6). |
| 5 | R1-5 Processing, retry, stop and categorized error states (summarized processing only; no chain-of-thought) | E: `b0f0fdc`, `4e0a9b3`; ErrorCard contrast: `959958b`, `777919a` | `handoffs/E.md` (44 chat tests); audit check "no chain-of-thought fields" in `QA_AUDIT_CLIENT.md` | Implemented. Error-card copy needs UX review (E handoff). |
| 6 | R1-6 Multiline composer: drafts, attachments (text only, D2), long-paste chips, keyboard support, optimistic send | E: `7b2d17e`, `c79920d`, `4cc6ca3`; IME and threshold fixes: `b8a4fff` | `handoffs/E.md`, `handoffs/QA1.md`, `mobile/test/qa/composer_keys_test.dart`, `mobile/test/qa/paste_chip_threshold_test.dart` | Implemented. Attachments are inlined text only; no upload (D2). |
| 7a | R1-7 (performance) Faster load, lazy heavy modules, batched stream updates, reliable motion | G: `efd44e7`, `6fd8bc1`, `50024bb` | `handoffs/G.md`, `perf/AFTER_STARTUP.md`, `perf/AFTER.md` (section 6.2) | Startup ordering merged. Cold-start after-numbers are host-VM proxies and do not measure `main()`. Batching is NOT demonstrated (section 6.2). |
| 7b | R1-7 (tokens, usage pill, a11y) Dark-mode token patch; inline 80% usage warning; reduced motion and transparency; a11y | F: `c9eb670`; a11y: `51960f6`, `959958b`, `777919a` | `handoffs/F.md` (no test results recorded in that handoff), `QA_A11Y.md` (section 7) | Implemented. Reduced-transparency and high-contrast fallbacks not separately asserted. |

Wiring and integration: Phase 2 `ChatWiring` (`f9d9a17` to `e6c0d57`) connects `ChatScreen` to `ChatController`. QA gap tests (`ee900ba`, `c9a9263`, `b1e570d`, `264c1e5`, `65e0175`), audit fixes (`59d4609`, `4b5ccb3`, `b8a4fff`, `8eb0f81`, `dd3d00a`, `2227b6f`), QA client fixes (`147b1ee`, `90586b6`, `9343b44`) and the final AUDIT-03/04/05 fixes (`4b95f5c`) are merged on the branch.

Contract deviations (contract §0, D1–D7) are tracked in `DEPENDENCY_BOARD.md`. Each has an R1.1 ticket in `R1_1_BACKLOG.md`.

## 3. Commits and diff

- Range `dcf4f75..release1/chat-redesign`: 63 commits (54 non-merge, 9 merge). Authoritative list: `git log --oneline dcf4f75..release1/chat-redesign`.
- Commits after the previous report (`9404fed`), newest first: `4b95f5c` (AUDIT-03/04/05 fixes and format), `6db4572` (merge r1/finalqa), `a834142` (QA report), `9343b44` (paste-test alignment), `90586b6` (AUDIT-01 regression fix and scroll tests), `8bba3eb` (merge), `777919a` (ErrorCard contrast), `959958b` (a11y contrast tokens and tab-order test), `51960f6` (a11y suites), `147b1ee` (AUDIT-01 and AUDIT-02 fixes), `28a30f4` (client audit), `16249fa` and `eda49f8` (perf AFTER docs).
- Diff stat, re-run 2026-10-22 at `4b95f5c`: `git diff --shortstat dcf4f75 release1/chat-redesign` = **223 files changed, 23,847 insertions(+), 660 deletions(-)**.
  - `mobile/`: 161 files, +15,078 / -618.
  - `tests/`: 11 files, +4,356.
- Since `9404fed`: 84 files changed, 1,696 insertions(+), 509 deletions(-).
- The head commit `4b95f5c` alone (`git show --shortstat`): 24 files changed, 313 insertions(+), 415 deletions(-). It contains a format pass and regenerated error-card a11y PNGs.
- Working tree outside the release diff (not part of R1, not touched): `docs/release-evidence/device/01-launch.png` modified; `Claude outputs/` and `docs/release-evidence/device/*.png` untracked. Preserved.

## 4. Test and check results

| Check | Command | Result | Source |
|---|---|---|---|
| Backend lint and secret scan | `make PYTHON=.venv/bin/python lint` | All checks passed; secret scan clean; exit 0 | re-run 2026-10-22, `4b95f5c` |
| Backend typecheck | `make PYTHON=.venv/bin/python typecheck` | Success: no issues found in 49 source files; exit 0 | re-run 2026-10-22, `4b95f5c` |
| Backend unit (incl. model-lab and web) | `make PYTHON=.venv/bin/python test-unit` | **226 passed**, 4 warnings; exit 0 | re-run 2026-10-22, `4b95f5c` (baseline 166) |
| Backend e2e | `make PYTHON=.venv/bin/python test-e2e` | **62 passed**, 2 warnings; exit 0 | re-run 2026-10-22, `4b95f5c` (baseline 51) |
| Backend Postgres integration | `make PYTHON=.venv/bin/python test-integration` (podman, postgres:17 and redis:8) | **6 passed**, 1 warning (starlette DeprecationWarning); exit 0 | re-run 2026-10-22, `4b95f5c` |
| Flutter analyze | `cd mobile && flutter analyze` | Clean at HEAD `4b95f5c` (reported by Supervisor-Release1Chat; not re-run by this package) | Supervisor message |
| Flutter whole suite incl. goldens | `cd mobile && TZ=Asia/Kolkata flutter test` | See `QA_REPORT.md` "Whole-suite result" (Supervisor run at HEAD `4b95f5c`). Earlier: 536 passed (WIRING handoff); 506 passed excluding goldens (QA, `9343b44`). | QA_REPORT |
| Flutter a11y | `cd mobile && TZ=Asia/Kolkata flutter test test/a11y/` | Earlier run 23 of 24 (ErrorCard contrast); later reported green by Supervisor: 103 passed across a11y and chat suites at HEAD (not re-run by this package). Final count: Supervisor run. | Supervisor message; QA_A11Y.md |
| Baseline pre-R1 (`dcf4f75`) | as above | backend unit 166, e2e 51, analyze clean, `flutter test` 340 | `perf/BASELINE_TEST_TIMINGS.md` |

This package did not run `flutter test`. It is the Supervisor's full-suite gate.

## 5. Backend audit resolution (`QA_AUDIT_BACKEND.md`)

All 10 findings are marked Fixed in that file's Resolution table.

| # | Severity | Title | Fix commit | Regression test |
|---|---|---|---|---|
| 1 | Critical | Cross-user access in continue and regenerate | `59d4609` | `tests/unit/test_r1_fix_stream_scope.py` |
| 2 | High | Cross-user replay in idempotency lookup | `59d4609` | `tests/unit/test_r1_fix_stream_scope.py` |
| 3 | High | Startup sweep leaves budget reservations locked | `4b5ccb3` | `tests/unit/test_r1_fix_streaming.py` |
| 4 | High | Unbounded StreamRegistry and stuck runs | `4b5ccb3` | `tests/unit/test_r1_fix_streaming.py` |
| 5 | Medium | Synchronous DB flush blocks event loop | `4b5ccb3` | `tests/unit/test_r1_fix_streaming.py` |
| 6 | Medium | MultipleResultsFound in idempotency check | `59d4609` | `tests/unit/test_r1_fix_stream_scope.py` |
| 7 | Medium | `after_seq` beyond buffer emits run.finished | `59d4609` | `tests/unit/test_r1_fix_stream_scope.py` |
| 8 | Low | Historical heartbeat burst on resume | `59d4609` | `tests/unit/test_r1_fix_stream_scope.py` |
| 9 | Low | Soft-deleted conversation continue and regenerate | `59d4609` | `tests/unit/test_r1_fix_stream_scope.py` |
| 10 | Low | Unused gateway admission slots leaked | `59d4609`, `4b5ccb3` | `tests/unit/test_r1_fix_streaming.py` |

Backend unit and integration results in section 4 are the re-run at HEAD.

## 6. Client audit resolution (`QA_AUDIT_CLIENT.md`) and performance

### 6.1 Client audit

| ID | Severity | Issue | Resolution | Commit |
|---|---|---|---|---|
| AUDIT-01 | High | Stream not cancelled on conversation switch; transcript lost on fetch failure | Fixed: owned stream stopped before messages fetch; fetch failure keeps prior transcript. Tests: `mobile/test/qa/high_audit_fixes_test.dart`, `mobile/test/qa/scroll_screen_test.dart` | `147b1ee`, regression `90586b6` |
| AUDIT-02 | High | Drafts survive sign-out on a shared device | Fixed by clearing `draft.v1.*` on sign-out, not per-user key scoping. **Residual:** two accounts on one device with no sign-out between them would share `draft.v1.new`. | `147b1ee` |
| AUDIT-03 | Medium | Rename dialog `TextEditingController` never disposed | Fixed: controller disposed with the dialog | `4b95f5c` |
| AUDIT-04 | Medium | `hasNewContent` not passed to `JumpToLatestButton`; "New messages" state never shown | Fixed: `hasNewContent` wired through | `4b95f5c` |
| AUDIT-05 | Low | Attachment remove target 24x24dp | Fixed: 48dp target | `4b95f5c` |

The AUDIT-03, -04 and -05 fixes were made at `4b95f5c` in response to rejection round 1. This package did not run their dedicated tests; the Supervisor's full-suite run is the gate for them.

### 6.2 Performance: before and after

Source for "after": `docs/release1/perf/AFTER.md` (`e9dd199`, two runs). Source for "before": `docs/release1/perf/BASELINE.md` (`dcf4f75`). **All numbers are host-VM widget-test proxies, not device measurements.** AFTER was measured before `4b95f5c`; the AUDIT-03/04/05 change does not touch the measured paths, but this is not re-measured.

| Metric | Before (`dcf4f75`) | After (`e9dd199`, run 1 / run 2) |
|---|---|---|
| Cold start proxy, `pumpApp` median (n=7) | 313 ms (run 1), 337 ms (run 2) | 215.3 ms / 209.8 ms |
| Cold start proxy, `pumpApp` p95 (n=7) | 1521 ms (run 1), 2075 ms (run 2) | 2022.3 ms / 1359.9 ms |
| Chat list scroll frame pump, median (90 frames) | 0.11 ms | 0.11 ms / 0.11 ms |
| Chat list scroll frame pump, p95 (90 frames) | 5.26 ms | 7.86 ms / 7.85 ms |
| Rebuilds per send, filtered (ChatScreen, MessageBubble, _UserRow, Composer) | median 9 (range 3 to 15) | median 20 (11, 18, 20, 22, 24), both runs |
| Rebuilds per send, unfiltered | not measured before | NOT MEASURED |
| Streaming frame timing | NOT MEASURED | NOT MEASURED (fake backend emits one delta per reply) |
| Device or profile frame timings, jank | NOT MEASURED | NOT MEASURED (no device) |
| Release APK size | NOT MEASURED | NOT MEASURED |
| Backend p50 latency | NOT MEASURED | NOT MEASURED |

Interpretation:
- Cold start is noise-dominated at n=7 and must not be read as an improvement or regression. The `main()` path (G's changes) is not exercised by `pumpApp`.
- Scroll median is unchanged. Scroll p95 rose from 5.26 ms to about 7.85 ms under this harness; 90 frames gives a noisy p95, and a harness difference is not ruled out.
- Filtered rebuilds per send rose from median 9 to 20. The perf test measures rebuilds per send, not per streamed delta, so it does not test batching.
- **Batching claim: not supported.** No measurement in this release shows fewer rebuilds from batching. Per-delta batching needs a multi-delta fake stream, which is not in this release.

Reproduce: `docs/release1/perf/measure.sh [repo-root]` (host-VM benchmarks plus release APK size). The release APK build was skipped in the measured session (did not finish; `perf/AFTER.md` line 24); APK size NOT MEASURED.

## 7. Accessibility (`docs/release1/QA_A11Y.md`)

Suites: `mobile/test/a11y/a11y_semantics_test.dart`, `a11y_keyboard_test.dart`, `a11y_golden_test.dart` (16 golden PNGs in `mobile/test/a11y/goldens/linux/`).

- Earlier recorded run (`51960f6` plus `959958b`): **23 of 24 passed**. The one failure was `ErrorCard and UsageWarningPill pass contrast in light and dark` (light Retry pair 4.40:1, WCAG 1.4.3). Supervisor reports this now passes at HEAD: a11y and chat suites 103 passed.
- `959958b` added explicit `errorContainer` and `onErrorContainer` tokens (light `#FDE8E8` / `#7A141E`, dark `#4A0E14` / `#FFDAD6`). `777919a` removed the blended border on the Retry button and regenerated error goldens. The fix is in branch history; the a11y suite was not re-run by this package at HEAD. Authoritative HEAD result: `QA_REPORT.md`.
- Keyboard suite (Enter, Shift+Enter, Tab order composer, attach, send; Esc retains focus): 4 of 4 at `51960f6`. Esc has no dismiss handling in `lib/`; the test asserts focus retention only.
- Not covered: reduced-transparency and high-contrast fallbacks beyond existing environment coverage; macOS and Windows golden baselines (goldens are Linux-only).
- The composer focus-traversal change (`FocusTraversalGroup`) is about 120 lines in `composer.dart`; review it as part of the diff.

## 8. Screenshots and goldens

- No device screenshots were produced by R1. Pre-existing untracked files in `docs/release-evidence/device/` predate R1 and are not R1 evidence.
- Goldens regenerated (27 files under `mobile/test/goldens/linux/`): chat, chat_empty, settings_dark, tier_chat sets, and `glass_legibility_dark.png` (rim alpha 0.18, `d705ac5`). New: `mobile/test/features/chat/rendering/goldens/markdown_message_basic.png`. Error-card a11y goldens regenerated in `959958b`, `777919a`, and `4b95f5c`.
- **Goldens have not been visually reviewed.** This is an open item (section 10).

## 9. Rollback (contract §10)

- Migrations are additive: `c7a1d2e3f405` (stream_runs), then `d8b2e3f4a516` (conversations). Downgrade drops only the new columns and tables. No backfill.
- No production deploy or migration in R1. Verification used local Postgres 17 via `make test-integration`.
- Rollback: revert the release commits in reverse merge order, then `alembic downgrade 5f708192a3b4`. The old mobile build keeps working because legacy routes are unchanged (`POST /v1/messages`, `POST /v1/runs/{id}/regenerate`, `POST /v1/runs/{id}/feedback`; contract D6).
- Stream routes are not behind a flag. Rollback is a code revert.
- Not executed: no rollback was performed or rehearsed in this release.

## 10. Unresolved risks

1. **Device and profile performance unmeasured.** No device. Frame timings, jank, streaming frame timing and launch-to-first-frame are NOT MEASURED. Host-VM numbers are not device budgets.
2. **Batching not demonstrated** (section 6.2). The perf test does not exercise per-delta streaming.
3. **APK size unmeasured.**
4. **Goldens need human review** (section 8; R-9 on the board).
5. **Postgres integration coverage is 6 tests** (connectivity, migrations round trip, conversation lifecycle). Not a full API integration suite.
6. **Real provider streaming (D4)**: whether OpenCode streams or sends a single delta is NOT VERIFIED from the A handoff.
7. **Resume is process-lifetime only (D5).** A restart marks runs `interrupted`; the user resumes via Continue. Multi-instance fan-out is out of scope.
8. **Medium and expanded layouts** are verified only by widget tests at 400, 800 and 1200 widths.
9. **Error-card copy** needs UX review (E handoff).
10. **Clerk on the critical path** when `CLERK_PUBLISHABLE_KEY` is set (G handoff); startup depends on the network in that case.
11. **Search is substring only** (D7). **Attachments are text-only, inlined** (D2). **Drafts are device-local** (D3).
12. **AUDIT-02 residual**: two accounts on one device without sign-out share `draft.v1.new`.
13. **Squad F file layout**: motion and transparency helpers live in `lib/theme/karmi_motion.dart`, not the §6 paths. Not a behaviour gap.
14. **Skipped QA client tests**: QA1 reported 2 xfail/skip in `mobile/test/qa/`; FIX un-xfailed `composer_keys_test.dart` and `paste_chip_threshold_test.dart`. The current skip count is in the Supervisor's full-suite run.

## 11. PENDING-USER: checks not passed and not attempted

These checks were NOT run by any agent in this release. They are required before a production or store release. Nothing below is claimed as passed.

- **Manual device or emulator run**: launch, chat send and stream, Stop, Continue, Regenerate, rotate or resize, keyboard, and history rail on a real Android or iOS device or emulator. Not attempted.
- **Real provider and real model**: end-to-end stream against a live provider (OpenRouter-compatible or OpenCode) with a real key. Not attempted. All tests used fake backends or synthetic prompts. No live charges, no real messages.
- **Auth sign-in**: Clerk sign-in, sign-out (which clears drafts, AUDIT-02), and token refresh on device. Not attempted.
- **Onboarding flow**: onboarding is R1.1 scope and is not implemented in R1. Listed so that it is not forgotten at R1.1 start. Not attempted.
- **Profile, settings, usage center**: R1.1 scope. Not attempted.

## 12. R1.1 backlog

Items deferred from R1 are in `docs/release1/R1_1_BACKLOG.md`: R1.1-1 to R1.1-5 (including onboarding, profiles, settings, usage center, and Artifact and Sources drawers within R1.1-5), and R1.1-6 to R1.1-11 (follow-ups for deviations D1 to D7). R1.1 MUST NOT start until the gate in `DEPENDENCY_BOARD.md` ("Gating on R1") is met, including the QA_REPORT regression gate.

## 13. Sign-off

Not signed in this document. Sign-off requires `docs/release1/QA_REPORT.md` approval by Manager-QAReleaseLead (SCOPE_TIMELINE, Phase 2 gate), with the PENDING-USER items in section 11 explicitly accepted or scheduled by the user.
