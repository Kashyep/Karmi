# R1 perf after startup work (Squad G)

Branch `r1/g` (worktree of `release1/chat-redesign`). Companion to `BASELINE.md`.

## Status: cold-start re-measurement BLOCKED

`mobile/test/perf/chat_perf_test.dart` does not compile on the current `release1/chat-redesign` tree, so no new PERF numbers could be produced:

```
lib/features/chat/chat_screen.dart:314:27: Error: No named parameter with the name 'onSend'.
  Compilation failed for testPath=.../test/perf/chat_perf_test.dart
```

Cause: wave 1 Squad E replaced `Composer` (`composer.dart`: now `draftKey`, `busy`, `onSubmit`). `chat_screen.dart` still calls the old `Composer(onSend: ..., isPending: ...)`. That file is Phase 2 (`ChatWiring`), not yet landed. The same error blocks every test that loads the app harness (verified: `test/features/tester_notice_test.dart` fails identically on the unmodified branch HEAD `efd44e7`).

Unblock: land Phase 2 `ChatWiring`, then run `docs/release1/perf/measure.sh <worktree>`.

## Important: the cold-start proxy does not measure `main()`

The proxy is `pumpApp` (test harness), which builds the app directly. It bypasses `main.dart`, so it cannot observe Clerk/glass/prefs startup ordering at all. Even once it compiles, it will not show any effect of the G changes. A real measurement needs a device/profile run (`flutter run --profile`, launch-to-first-frame via DevTools timeline or `flutter drive`), which is not available in this session.

## Baseline numbers (from BASELINE.md, unchanged, for reference)

| Metric | Baseline |
|---|---|
| Cold start proxy (`pumpApp`, host VM) | median 337 ms, p95 2075 ms (run 1: 313 / 1521 ms) |
| Chat scroll frame pump (host VM) | median 0.11 ms, p95 5.26 ms |
| Rebuilds per send (filtered) | median 9 |
| Release APK size | NOT MEASURED |
| Device jank / backend latency | NOT MEASURED |

## Lint fix in the perf test

`flutter analyze test/perf/chat_perf_test.dart` reported 6 issues (not 12) on this tree: 3 unnecessary imports, 1 unused `dart:convert`, 1 unused `package:http`, 1 `avoid_print`. Fixed: removed the unused/redundant imports; `avoid_print` suppressed with an explicit `// ignore` (the `PERF ` line output is the contract for `BASELINE.md` capture). Result: `flutter analyze` on the file, `lib/main.dart`, `lib/app.dart`: No issues found.

## Reproduce once unblocked

```
export PYTHON=/home/rosso/Projects/Karmi/.venv/bin/python
cd <worktree> && TZ=Asia/Kolkata docs/release1/perf/measure.sh <worktree>
```
