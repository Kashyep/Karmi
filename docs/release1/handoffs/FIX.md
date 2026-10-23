# FIX handoff (Manager-AuditFix)

Branch `r1/fix` (worktree /tmp/wt-fix). Not merged.

## Commits
- 59d4609 fix(r1/fix): stream and conversation scoping (audit 1, 2, 6, 7, 8, 9, 10 route)
- 4b5ccb3 fix(r1/fix): streaming registry, sweep, runner flush and slot return (audit 3, 4, 5, 10 runner)
- b8a4fff fix(r1/fix): composer IME Enter and strict paste threshold (QA1 client items)
- 8eb0f81 test(r1/fix): conversations Postgres integration and migration round trip
- docs(r1/fix): audit resolution and FIX handoff (this commit; see `git log` on r1/fix)

## Results
- Integration: `make test-integration` 6 passed (IntegrationPg worker).
- Client: `flutter test test/qa/composer_keys_test.dart test/qa/paste_chip_threshold_test.dart` 7 passed.
- Backend: pytest unit streaming subset 31 passed before lint commit.

## Checks for main agent
- `make PYTHON=.venv/bin/python lint`
- `make PYTHON=.venv/bin/python typecheck`
- `make PYTHON=.venv/bin/python test-unit`
- `make PYTHON=.venv/bin/python test-e2e`
- `make PYTHON=.venv/bin/python test-integration`
- `cd mobile && flutter test test/qa --exclude-tags golden`

## Notes
- Opt-out: ComposerIME did not touch chat wiring files (chat_screen, message_bubble, chat_entry, status_chip, app.dart).
- Per-finding resolution and regression tests: docs/release1/QA_AUDIT_BACKEND.md "Resolution" section.
