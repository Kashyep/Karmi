# Release 1 — Accessibility QA

Branch `r1/a11y` (worktree `/tmp/wt-a11y`, based on `release1/chat-redesign`). Not merged.

## Scope
- Semantics labels and tap targets (>= 48dp), contrast, and screen-reader order: `mobile/test/a11y/a11y_semantics_test.dart`.
- Keyboard (Enter, Shift+Enter, Tab traversal, Esc): `mobile/test/a11y/a11y_keyboard_test.dart`.
- Text scale 2.0 without overflow and golden coverage (light/dark, chat, error card, processing panel): `mobile/test/a11y/a11y_golden_test.dart`, baselines in `mobile/test/a11y/goldens/linux/` (16 PNGs).
- Run with `TZ=Asia/Kolkata flutter test test/a11y/`.

## Results
| Suite | Tests | Pass | Fail |
|---|---|---|---|
| a11y_golden_test.dart | 19 | 19 | 0 |
| a11y_semantics_test.dart | (shared run) | — | 1 |
| a11y_keyboard_test.dart | (shared run) | — | 1 |
| **Total (`test/a11y/`)** | **24** | **22** | **2** |

## Lib edits (minimal a11y fixes)
- `mobile/lib/features/chat/error_card.dart`: contrast adjustment for error-card text/action colors (attempted fix for WCAG).
- `mobile/lib/widgets/usage_warning_pill.dart`: narrowed `ExcludeSemantics` so the label text (not the whole container) is the semantic node.
- `mobile/lib/features/chat/composer.dart`: `FocusTraversalGroup` with `OrderedTraversalPolicy` for composer -> attach -> send order. The diff is larger than a single wrap (~120 lines changed in the file); review before merge.

## Open defects (failing tests)
1. **Error-card contrast (WCAG 1.4.3)**: `ErrorCard and UsageWarningPill pass contrast in light and dark` fails. Retry label measures 4.40:1 (need 4.5:1) at 14sp on the light error container. The `error_card.dart` change did not close the gap; fix the foreground/background token pair.
2. **Tab focus order**: `Tab traversal across composer -> attach -> send is in order` fails: after the expected Tab step, focus is not on the Attach button. The composer traversal group change does not yet reach the attach control; needs a focus-node trace.

No Esc dismiss handling exists in lib; the Esc test asserts focus retention only.

## Not verified
- Reduce-transparency and high-contrast fallbacks were not separately asserted in the golden suite beyond existing Env coverage.
- Goldens are Linux-only (host OS path); no macOS/Windows baselines.
- Whole-suite, analyze, and perf were not run by this package.
