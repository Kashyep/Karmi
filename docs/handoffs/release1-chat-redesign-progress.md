# Release 1 chat redesign — temporary progress

Updated: 2026-10-23 14:02 UTC  
Integration worktree: `/tmp/wt2-int`, branch `release1/integration`, HEAD `4ec67f7`  
Policy: no supervisor system; low-cost Luna workers only. No push, deploy, hosted migration, live provider calls, paid spend, or PR action.

## Verified / locally integrated

- P1 history base `c0a529e`; worker found and fixed stored replies over the external 8,000-character DTO cap (`fedc2b1`). Focused long-Hindi streaming regression passes.
- P6 app bar/banner commits integrated through `20d82bf`; integrated app-bar + device-regression Flutter tests: 25 passed. Candidate analysis passed.
- P9 suggestion chips `9338561` is present on integration; worker verified 5 focused tests and analyzer.
- P10's stale streaming xfail is replaced with a mocked long-Hindi stream check. Zero live budget now has a no-call/no-output test. Focused tests pass.
- P2's unapproved zero-score exclusion was reverted (`f5d2794`) per owner instruction. P4 is not integrated.
- Backend baseline before latest changes: lint and strict typecheck passed; unit 247 passed; e2e 83 passed, 1 skipped, 1 obsolete xfail. Rerun full gates after mobile integration.

## In progress / not accepted

- P3 renderer: existing candidate plus preserved local entity-decoding/test edits in `/tmp/wt2-3`; one-pass decode needs focused tests/goldens and review.
- P5 composer/status: worker candidate `ab71f47` is **not accepted**. Boss found same-ID retry would replay the terminal run, and keyboard inset units need a non-1.0 DPR test. Rework requested.
- P6 is integrated, but P5 changes overlap `chat_screen.dart` and `karmi_shell.dart`; rerun P6 tests after P5 integration.

## Blocked / not started

- P2: exact free-model/task exclusions await owner instruction; no policy change accepted.
- P4: authorized tester identity awaits owner instruction; debug metadata/migration not integrated.
- P7/P8: start after P5 is accepted; neither is implemented/verified.
- Local Clerk test-auth path and state-aware local device harness need audit/implementation. Never read `.env.testauth`; code value must not enter source, logs, tests, screenshots, or Git history.
- Pixel 9a is connected, but device runs wait until all required automated gates pass and the local test-auth/harness path is verified.
- No integrated APK/build, complete Flutter suite, integration test, or device evidence yet.

## Next actions

1. Finish P5 rework and Boss acceptance; then implement P7 and P8 in scoped worktrees.
2. Validate/integrate P3 and audit auth/device harness; rerun lint, typecheck, unit, e2e, Flutter analyze/tests/goldens, and available integration gates.
3. Build the local-backend test APK and record actual Pixel observations/screenshots only after automated gates pass. Keep P2/P4 blocked pending owner values.
