# Discovery 04 — Test and release audit (PHASE 0, read-only)

Source: explorer SpottyGoldfish, 2026-10-21.

## Backend
- 211 pytest tests in 30 files: tests/unit 121 (19 files), tests/model_lab 24 (2), tests/web 11 (1), tests/e2e 51 (7), tests/integration 4 (1). Markers `integration`, `e2e` (pyproject.toml:50-53).
- Baseline: 166 unit/model_lab/web passed; 51 e2e passed. One anyio BlockingPortal DeprecationWarning.
- Commands: `make PYTHON=.venv/bin/python lint` (ruff check src tests scripts + scripts/secret_scan.py); `typecheck` (mypy src, strict); `test-unit`; `test-e2e`; `test-integration` (Postgres 17 :55432, Redis 8 :56379 via podman/docker); `benchmark-demo`; `test-release` (all sequentially).

## Flutter
- 15 test files in mobile/test + fonts_test.dart + flutter_test_config.dart + support/{harness,fake_backend}.dart. Baseline 340 tests passing (recorded by QA).
- Commands (in mobile/): `dart format --output=none --set-exit-if-changed .`; `flutter analyze`; `flutter test --exclude-tags golden`; `TZ=Asia/Kolkata flutter test --tags golden`; regenerate `TZ=Asia/Kolkata flutter test --update-goldens --tags golden`.
- Goldens: 82 in mobile/test/goldens/linux (64 screen variants, 16 tier-theme, 2 glass floor). Windows set has 90 under goldens/windows.
- TZ: flutter_test_config.dart does NOT set timezone. Without TZ=Asia/Kolkata, 8 golden mismatches (32 diffs in mobile/test/failures/) due to 05:30 IST reset display.

## CI (.github/workflows/ci.yml)
- `checks` (ubuntu, Py 3.12): uv lock consistency, lint, typecheck, test-unit, test-e2e, benchmark-demo, test-integration.
- `mobile-checks` (ubuntu, Java 17, Flutter 3.47.5): pub get, dart format, analyze, test excluding golden, golden under TZ=Asia/Kolkata, appbundle release build.
- `mobile-ios-build` (macos): ipa --no-codesign.

## Release evidence conventions
- docs/release1/TEST_STRATEGY.md, docs/release1/perf/BASELINE_TEST_TIMINGS.md, docs/release-evidence/*.md. Unexecuted gates marked `NOT RUN: <reason>`. Screenshots in docs/release-evidence/device/*.png (preserve; do not delete).
- Golden updates restricted to QA squad on Linux, commit prefix `golden:`.
- Additive-only migrations.

## Missing R1 test categories (QA owns; file suggestions)
1. Streaming: tests/unit/test_streaming.py, tests/e2e/test_stream_api.py, mobile/test/api/stream_api_test.dart, mobile/test/features/stream_interruption_test.dart.
2. Persistence/search: tests/unit/test_conversations.py, tests/unit/test_conversation_search.py, tests/e2e/test_conversations_api.py, mobile/test/features/conversation_list_test.dart, mobile/test/features/draft_persistence_test.dart.
3. Composer: mobile/test/features/composer_paste_test.dart, composer_keyboard_test.dart.
4. Scroll and layout: mobile/test/features/chat_scroll_behavior_test.dart, workspace_layout_test.dart.
5. Dark tokens and a11y: mobile/test/theme/dark_mode_tokens_test.dart, mobile/test/features/usage_warning_test.dart.

## QA baseline (recorded by Manager-QAReleaseLead)
- backend unit 166 passed, e2e 51 passed, lint/typecheck clean; flutter analyze clean; flutter test 340 passed under IST.
