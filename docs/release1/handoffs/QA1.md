# QA1 handoff (Manager-QAGap)

Branch `r1/qa` (worktree /tmp/wt-qa, from release1/chat-redesign f2aabf6). Not merged.

## Commits
- ee900ba test(r1/qa): backend stream and conversations gap tests
- c9a9263 docs(r1/qa): backend streaming audit (docs/release1/QA_AUDIT_BACKEND.md)
- b1e570d test(r1/qa): client gap tests (mobile/test/qa/)

## Results
- Backend gap tests: `tests/unit/test_r1_qa_stream_conversations_gaps.py` 9 passed, 0 failed.
- Client gap tests: `cd mobile && flutter test test/qa --exclude-tags golden` 44 passed, 2 xfail/skip, 0 failed.
- Integration: `make test-integration` (podman, postgres:17-alpine + redis:8-alpine) 4 passed, 1 warning (starlette DeprecationWarning). Run on main checkout's `.venv`. Note: existing integration file only covers connectivity; it does not yet exercise migrations c7a1d2e3f405/d8b2e3f4a516 or conversations against real Postgres (contract §8/§3.2 gap).

## Bugs found (src not edited by QA)
1. Critical (audit): `routes/stream.py:161,168,177,332,380,405,526` scope by `account_id` only; conversations service scopes by `user_id` too. Another user in the same account can continue/regenerate/replay runs. Fix: add `user_id` to these filters, 404 on mismatch. Contract §3 "every query scopes to caller's user_id".
2. High (audit): `streaming/registry.py:65-82` unbounded run registry; `streaming/registry.py:98-114` startup sweep leaves budget reservations locked. See QA_AUDIT_BACKEND.md for full list (10 findings).
3. `mobile/lib/features/chat/composer.dart:88` Enter handler does not check IME composition (`composing.isValid`); Enter during IME candidate selection sends. Contract §8 / TEST_STRATEGY §3.3. xfail test in mobile/test/qa/composer_keys_test.dart.
4. `mobile/lib/features/chat/composer.dart:155` paste chip uses `diff >= longPasteThreshold`; contract says over threshold (2500 chars must not chip). Boundary bug, low. xfail in mobile/test/qa/paste_chip_threshold_test.dart.

## Gap analysis (contract §8 vs tests)
Covered before QA: stream runner/registry/sse/routes unit, conversations routes/service unit, e2e release1 stream/conversations, sse parser basics, chat widget tests, usage pill, colours.
Added: disconnect-does-not-cancel, buffer eviction to resume_unavailable, budget settled once, LIKE escaping, search pagination, cross-user search isolation; sse edge cases, draft per conversation, paste threshold, Enter/Shift+Enter, markdown HTML/javascript: safety, contrast, usage pill 0.8, reduced motion.
Still missing: ChatController tests (batching, stall, length→Continue, error categories) — ChatController is not covered by QA1; scroll pinning and Jump to Latest widget tests (chat_screen-dependent or not yet written); Dart draft persistence across app restart with real store; e2e for continue/regenerate idempotency cross-user.

## Checks for main agent
- `make PYTHON=.venv/bin/python test-unit` including new gap file
- `cd mobile && flutter test test/qa --exclude-tags golden`
- `make PYTHON=.venv/bin/python test-integration` (passed here)
