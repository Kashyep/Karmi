# Handoff G: performance (client startup, perf test hygiene)

Branch `r1/g`. Owned: `mobile/lib/main.dart`, `mobile/lib/app.dart`, plus `docs/release1/perf/AFTER_STARTUP.md` and this file.

## Decisions (contract §6 G)

- **Clerk init: parallel, not deferred.** `KarmiSession` takes `ClerkAuthState` at construction and wires the token provider in its constructor (`auth/session.dart`, not owned by G). Deferring Clerk until the auth screen would require changing session construction, so it stays in the parallel `Future.wait` before `runApp`.
- **Deferred imports (`deferred as`): not used.** Every first-frame screen (`WelcomeScreen`, `KarmiShell`, `TesterNoticeScreen`) is imported eagerly by `app.dart`, so no startup-path code is lazily reachable. Settings/usage/onboarding screens are reached from the shell (not owned by G), so deferring them from `main.dart`/`app.dart` is not possible within G's files. [INFERENCE] Dart deferred loading gives no first-frame win on native AOT without deferred components; not verified on device.
- `app.dart`: unchanged.
- `main.dart`: unchanged logic; comment documents the above.
- Backend: nothing added in G (contract §6: G adds nothing else in R1).

## Checks

- `flutter analyze test/perf/chat_perf_test.dart lib/main.dart lib/app.dart`: No issues found (was 6 issues in the perf test: unused imports, `avoid_print`).
- Cold-start re-measurement: BLOCKED. `chat_perf_test.dart` and every test importing the app harness fail to compile on `release1/chat-redesign` HEAD (`chat_screen.dart:314` still uses old `Composer(onSend:)`; Phase 2 `ChatWiring` not landed). Verified pre-existing on `efd44e7` via stash. Also, `pumpApp` bypasses `main()`, so the proxy would not measure these startup changes. See `docs/release1/perf/AFTER_STARTUP.md`.

## For main agent

- After Phase 2 lands: run `flutter test` (full) and `docs/release1/perf/measure.sh`; update AFTER_STARTUP.md.
- Real startup numbers need a profile device run (launch to first frame); not available here.

## Risks

- Clerk remains on the critical path to first frame when `CLERK_PUBLISHABLE_KEY` is set (network-dependent init).
