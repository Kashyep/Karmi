import 'package:flutter/material.dart';

import 'karmi_motion.dart';

/// Single source of truth for Karmi design tokens that are not tier colours:
/// motion durations, spacing, usage-warning colours and the dark specular
/// border alpha.
///
/// Other squads MUST NOT hardcode colours or durations; they MUST read them
/// from here (or from `KarmiColors` for tier-dependent colours).
abstract final class KarmiTokens {
  // Durations. Use [motion] so reduced-motion settings are honoured.
  static const Duration fast = Duration(milliseconds: 120);
  static const Duration standard = Duration(milliseconds: 180);
  static const Duration slow = Duration(milliseconds: 240);

  /// [normal] under normal motion, [Duration.zero] when reduced motion is on
  /// (platform `disableAnimations` or the in-app [KarmiAccessibility] flag).
  static Duration motion(BuildContext context, [Duration normal = standard]) =>
      KarmiAccessibility.reduceMotionOf(context) ? Duration.zero : normal;

  // Spacing scale (logical pixels).
  static const double s4 = 4;
  static const double s8 = 8;
  static const double s12 = 12;
  static const double s16 = 16;
  static const double s24 = 24;
  static const double s32 = 32;

  /// Usage fraction at which the usage warning pill appears.
  static const double usageWarningThreshold = 0.8;

  /// True when [fraction] of the allowance is used up to the warning level.
  /// NaN is never a warning.
  static bool isUsageWarning(double fraction) =>
      fraction >= usageWarningThreshold;

  /// Alpha of the glass rim stroke. Dark mode uses a stronger specular edge so
  /// the rim stays visible on dark backdrops; light mode keeps 0.10.
  static double specularBorderAlpha(Brightness brightness) =>
      brightness == Brightness.dark ? 0.18 : 0.10;

  /// Usage warning pill background.
  /// Contrast: foreground ≥4.5:1, icon ≥3:1 against this fill in both modes.
  static Color usageWarningFill(Brightness brightness) =>
      brightness == Brightness.dark
      ? const Color(0xFF3A2A07)
      : const Color(0xFFFEF3C7);

  /// Usage warning pill label colour.
  static Color usageWarningForeground(Brightness brightness) =>
      brightness == Brightness.dark
      ? const Color(0xFFFDE68A)
      : const Color(0xFF78350F);

  /// Usage warning pill icon colour.
  static Color usageWarningIcon(Brightness brightness) =>
      brightness == Brightness.dark
      ? const Color(0xFFFBBF24)
      : const Color(0xFFB45309);
}
