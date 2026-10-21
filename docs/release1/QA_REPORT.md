# Karmi R1 Final QA Report

Branch: `r1/finalqa` (worktree `/tmp/wt-finalqa`), based on `release1/chat-redesign` e9dd199. Not merged by this package.

## Verdict

**GO for the R1 chat client, with 3 open non-blocking client findings (1 Medium-level UI bug, 1 Medium leak, 1 Low tap-target) recorded below.** No Critical or High client finding remains open. Backend Critical/High items are marked fixed in `QA_AUDIT_BACKEND.md`.

## Whole-suite result

- `cd mobile && TZ=Asia/Kolkata flutter test --exclude-tags golden` on `9343b44`: **506 passed, 0 failed, exit 0**.
- The first run of the same suite failed one test (`composer_test.dart`, "paste >= 2500 chars becomes chip"). Cause: commit b8a4fff made the paste threshold strict (`diff > longPasteThreshold`) but did not update that test. Fixed in `9343b44` by aligning the test to strict >2500.

## Client audit (`QA_AUDIT_CLIENT.md`)

| ID | Severity | Status | Notes |
|---|---|---|---|
| AUDIT-01 | High | Fixed (147b1ee, regression fix in 90586b6) | Owned stream is stopped before the conversation messages fetch. Fetch failure keeps the prior transcript. Tests: `mobile/test/qa/high_audit_fixes_test.dart`. |
| AUDIT-02 | High | Fixed (147b1ee) by clearing `draft.v1.*` on sign-out, not by per-user key scoping | Drafts no longer survive sign-out. Known residual: two accounts on one device without a sign-out between them would still share the `draft.v1.new` key. |
| AUDIT-03 | Medium | Open | `history/conversation_actions.dart:89` rename-dialog `TextEditingController` is never disposed. |
| AUDIT-04 | Medium | Open | `chat_screen.dart:428-432` does not pass `hasNewContent` to `JumpToLatestButton`, so the "new messages" state never shows. Found again during screen tests. |
| AUDIT-05 | Low | Open | `composer/attachment_chip.dart:60` remove target is 24x24dp, below 48dp. |

Checks that passed in the audit: no chain-of-thought fields in models or UI, HTML escaped in markdown, `javascript:`/`data:`/`file:` links rejected, no auto-launched links, stream and timer disposal in `ChatController`, `ConversationListController`, and `EndAnchoredScroll`.

## QA1 open gaps (`handoffs/QA1.md`)

- ChatController tests: already present from earlier QA work.
- Scroll pinning during streaming at screen level: added in `mobile/test/qa/scroll_screen_test.dart` (2 tests).
- Jump to Latest at screen level: added in the same file. Note this covers visibility, semantics label, and tap-to-end. The `hasNewContent` badge (AUDIT-04) is still not wired.
- Still not covered: Dart draft persistence across an app restart with the real store; cross-user e2e for continue/regenerate (backend tests cover the scoping fix).

## Backend (from `QA_AUDIT_BACKEND.md`)

Critical 1 and High 3 are marked fixed in that document with test references. Not re-verified in this package.

## Perf (`perf/AFTER.md`)

Host-VM proxies only, not device numbers. Cold-start proxy and scroll p95 are noisy at this sample size. Filtered rebuilds per send rose from a median of 9 to 20. That is a regression signal under the same method. It does not support a batching improvement claim, because the perf test does not exercise per-delta streaming. APK size, unfiltered rebuilds, streaming frame timing, and device jank are NOT MEASURED.

## Commits (r1/finalqa)

- 16249fa, eda49f8, 28a30f4: perf AFTER and client audit docs
- 147b1ee: AUDIT-01 and AUDIT-02 fixes
- 90586b6: AUDIT-01 regression fix and screen scroll tests
- 9343b44: composer paste-threshold test alignment

## Items to check on merge

1. Merge 90586b6 and 9343b44 (147b1ee was already merged).
2. Run the whole suite once after merge. Last run on this branch: 506 passed.
3. Decide whether AUDIT-03/04/05 are accepted for R1 or get a follow-up ticket. AUDIT-04 is a one-line wiring fix.
