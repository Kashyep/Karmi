# Squad F handoff: design tokens, dark specular, usage warning pill

## New files
- `mobile/lib/theme/karmi_tokens.dart`: `KarmiTokens` (single source for non-tier tokens).
- `mobile/lib/theme/contrast.dart`: `contrastRatio(Color, Color)` (WCAG 2.x).
- `mobile/lib/widgets/usage_warning_pill.dart`: `UsageWarningPill({fraction})`.
- `mobile/test/theme/karmi_tokens_test.dart`
- `mobile/test/widgets/usage_warning_pill_test.dart`

## Changed files
- `mobile/lib/theme/karmi_glass.dart`: rim stroke uses `_rimColor`. Dark brightness applies `KarmiTokens.specularBorderAlpha` (0.18) to `colors.glassBorder`; light keeps `colors.glassBorder` unchanged. Import of `karmi_tokens.dart` added.

## Token values
- Durations: fast 120ms, standard 180ms, slow 240ms. `KarmiTokens.motion(context, normal)` returns zero under reduced motion.
- Spacing: s4=4, s8=8, s12=12, s16=16, s24=24, s32=32.
- Usage warning threshold: 0.8. `isUsageWarning` is false for NaN.
- Specular border alpha: light 0.10, dark 0.18.
- Usage warning, light: fill `#FEF3C7`, foreground `#78350F`, icon `#B45309`.
- Usage warning, dark: fill `#3A2A07`, foreground `#FDE68A`, icon `#FBBF24`.
- Hand-checked contrast: light text ≈8.1:1, icon ≈4.5:1; dark text ≈11.1:1, icon ≈8.3:1.

## Deviations
- Motion helpers stay in `lib/theme/karmi_motion.dart` (`KarmiAccessibility`, `KarmiMotion`) so existing importers are not broken. The contract text named `theme/motion.dart` and `transparency.dart`; those were not created.
- `KarmiTokens.motion` delegates to `KarmiAccessibility.reduceMotionOf`.

## Golden tests likely affected
- Any golden that renders `KarmiGlassSurface` in dark mode with the rim visible (glass rim alpha changed from the tier `glassBorder` alpha to 0.18 override). Not regenerated.
- Light-mode goldens are unchanged.

## Needs from other squads
- `UsageMeter` in `lib/features/usage` should render `UsageWarningPill(fraction: ...)`. Not F-owned.
- Other squads must read durations, spacing, and warning colours from `KarmiTokens`, not hardcode them.
