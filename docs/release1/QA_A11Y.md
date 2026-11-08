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
| a11y_semantics_test.dart | 1 | 0 | 1 |
| a11y_keyboard_test.dart | 4 | 4 | 0 |
| **Total (`test/a11y/`)** | **24** | **23** | **1** |

`test/features/chat` (regression, after lib edits): 79 pass, 0 fail. `flutter analyze lib/features/chat lib/theme lib/widgets test/a11y`: no issues.

## Lib edits (minimal a11y fixes)
- `mobile/lib/theme/karmi_theme.dart`: explicit `errorContainer` / `onErrorContainer` tokens in the light and dark ColorSchemes (light #FDE8E8 / #7A141E, dark #4A0E14 / #FFDAD6), replacing Material's default error container pair that measured 4.40:1 for ErrorCard Retry text. Error-card goldens regenerated.
- `mobile/lib/features/chat/error_card.dart`: no net change (earlier luminance hack reverted).
- `mobile/lib/widgets/usage_warning_pill.dart`: narrowed `ExcludeSemantics` so the label text (not the whole container) is the semantic node.
- `mobile/lib/features/chat/composer.dart`: `FocusTraversalGroup` with `OrderedTraversalPolicy` for composer -> attach -> send order. The diff is larger than a single wrap (~120 lines changed in the file); review before merge.

## Open defects (failing tests)
1. **Error-card contrast (WCAG 1.4.3)**: `ErrorCard and UsageWarningPill pass contrast in light and dark` still fails with the sampled light pair #EECCD0 at 4.40:1 for the Retry button, even after the token change (which applies through `KarmiTheme.of`). The sampled colour does not match the token, so the guideline is likely sampling the card surface blended with the glass/tint layer or the 0.3-alpha button border. Needs a pixel-level trace; not fixed.

Resolved this round: Tab traversal composer -> attach -> send now passes (the test had an invalid focus assertion and used an empty draft, where Send is disabled and unfocusable).

No Esc dismiss handling exists in lib; the Esc test asserts focus retention only.

## Not verified
- Reduce-transparency and high-contrast fallbacks were not separately asserted in the golden suite beyond existing Env coverage.
- Goldens are Linux-only (host OS path); no macOS/Windows baselines.
- Whole-suite, analyze, and perf were not run by this package.
