# Discovery 05 — Performance hot paths (PHASE 0, read-only)

Source: explorer ParallelMarten, 2026-10-21. **No device or frame timings were measured.** Before/after numbers are QAReleaseLead's job (docs/release1/perf/). Measured here: `flutter analyze` 0 issues in 8.4s; `prose_width_test.dart` 2 passed in 9.75s wall clock. Asset size: google_fonts 1.6 MB, app icons 36 KB. Source: 37 Dart files (5,990 lines) under mobile/lib; 36 Python files (7,017 lines) under src/.

## Startup
- mobile/lib/main.dart:14-27: three sequential awaits before runApp: LiquidGlassWidgets.initialize, SharedPreferences.getInstance, ClerkAuthState.create.

## Eager tab hydration
- shell/karmi_shell.dart:77-102: all four tab screens are built on launch inside IndexedStack.

## Chat rendering
- features/chat/chat_screen.dart:46,57,65,83: root setState for every transition.
- features/chat/message_bubble.dart:50-110: LayoutBuilder per bubble adds deferred layout passes.
- features/chat/chat_screen.dart:215-226: animateTo(maxScrollExtent) in postFrameCallback; will thrash under token streaming.
- features/chat/composer.dart:25: setState on every keystroke.

## Backend
- api.py:404-585 and services.py:703-760 are synchronous; two DB transactions per message; no per-token writes today.

## Risks for R1
- Per-token setState or per-token DB writes cause jank and pool exhaustion. Mitigation: batch deltas on a ~50 ms ticker in ChatController; persist partial_text at most once per second or per 1 KB.
