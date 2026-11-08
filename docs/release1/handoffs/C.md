# Squad C handoff: responsive workspace shell and end-anchored scroll (branch r1/c)

## New files
- `mobile/lib/shell/breakpoints.dart`: `WorkspaceSize` (compact <600, medium 600..1024 inclusive, expanded >1024), `workspaceSizeOf(double)`, `workspaceSizeOfContext(BuildContext)`.
- `mobile/lib/shell/workspace_layout.dart`: `WorkspaceLayout({required Widget rail, required Widget main})`. Compact returns main only; medium/expanded place rail left of main.
- `mobile/lib/features/chat/scroll/end_anchored_scroll.dart`: `EndAnchoredScrollController` (ChangeNotifier) with `isAtBottom`, `hasNewContent` (ValueListenable<bool>), `isPinned`, `jumpToLatest({Duration? duration, Curve curve, BuildContext? context})`; `EndAnchoredScroll({controller, builder, child, pinned, bottomThreshold})`.
- `mobile/lib/features/chat/scroll/jump_to_latest_button.dart`: `JumpToLatestButton({required visible, required onTap, hasNewContent = false})`.
- Tests: `mobile/test/shell/{breakpoints_layout_test,karmi_shell_layout_test,workspace_layout_test}.dart`, `mobile/test/features/chat/scroll/{end_anchored_scroll_test,jump_to_latest_button_test}.dart`.

## Changed files
- `mobile/lib/shell/karmi_shell.dart`: optional `historyRailBuilder` (additive, default null). Tabs are built on first visit and kept in an IndexedStack (state kept). Compact layout unchanged; medium adds NavigationRail; expanded with `historyRailBuilder` puts NavigationRail + history rail left of the body.

## Needs (for ChatWiring / integration)
- ChatWiring: wrap the chat transcript list with `EndAnchoredScroll` (builder form to attach the ScrollController), use `EndAnchoredScrollController.jumpToLatest`, and place `JumpToLatestButton(visible: !isAtBottom, hasNewContent: ..., onTap: jumpToLatest)` over the list.
- Wiring: pass `historyRailBuilder: (ctx) => ConversationList(controller: ..., ...)` into `KarmiShell` on medium/expanded.
- `chat_screen.dart` is not touched by Squad C.

## Checks (worker runs, branch r1/c)
- `flutter analyze lib/shell lib/features/chat/scroll test/shell test/features/chat/scroll`: no issues (shell worker and scroll worker reports).
- `flutter test test/features/chat/scroll`: 10/10 passed (5 end-anchored, 5 button).
- `flutter test test/shell`: 11 passed (shell worker report).
- Goldens: not regenerated; compact visuals intended unchanged.

## Risks
- Shell layout tests avoid compiling chat_screen.dart; full-app compile depends on Wiring.
- Medium/expanded layouts verified only with widget tests at 400/800/1200 widths, not on device.
