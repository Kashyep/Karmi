import 'package:flutter/material.dart';

/// Karmi design tokens (UI_IMPLEMENTATION_PLAN.md §2.2–2.3, Design.md).
///
/// Pairing rules that the contrast test (test/theme/karmi_colors_test.dart) pins:
/// - `accent` is never a text or icon colour on light surfaces; its foreground is
///   always `accentForeground` (dark text), never white.
/// - `secondary` is a fill colour only on light surfaces.
/// - `borderSubtle` is decorative and must never be the only boundary of a control.
@immutable
class KarmiColors extends ThemeExtension<KarmiColors> {
  const KarmiColors({
    required this.background,
    required this.foreground,
    required this.card,
    required this.cardForeground,
    required this.primary,
    required this.primaryForeground,
    required this.secondary,
    required this.secondaryForeground,
    required this.accent,
    required this.accentForeground,
    required this.muted,
    required this.mutedForeground,
    required this.border,
    required this.borderSubtle,
    required this.ring,
    required this.destructive,
    required this.destructiveForeground,
    required this.success,
    required this.warning,
  });

  final Color background;
  final Color foreground;
  final Color card;
  final Color cardForeground;
  final Color primary;
  final Color primaryForeground;
  final Color secondary;
  final Color secondaryForeground;
  final Color accent;
  final Color accentForeground;
  final Color muted;
  final Color mutedForeground;
  final Color border;
  final Color borderSubtle;
  final Color ring;
  final Color destructive;
  final Color destructiveForeground;

  /// Status icon colours kept from Design.md until branded ones exist. Always paired with a word.
  final Color success;
  final Color warning;

  static const light = KarmiColors(
    background: Color(0xFFF4FBF5),
    foreground: Color(0xFF08160A),
    card: Color(0xFFFFFFFF),
    cardForeground: Color(0xFF08160A),
    primary: Color(0xFF2C6D34),
    primaryForeground: Color(0xFFF4FBF5),
    secondary: Color(0xFF86D0AF),
    secondaryForeground: Color(0xFF08160A),
    accent: Color(0xFF42A980),
    accentForeground: Color(0xFF08160A),
    muted: Color(0xFFE6F2E8),
    mutedForeground: Color(0xFF4B5E4E),
    border: Color(0xFF6F8A72),
    borderSubtle: Color(0xFFD5E8D8),
    ring: Color(0xFF2C6D34),
    destructive: Color(0xFFB42332),
    destructiveForeground: Color(0xFFFFFFFF),
    success: Color(0xFF146B43),
    warning: Color(0xFF805000),
  );

  static const dark = KarmiColors(
    background: Color(0xFF08160A),
    foreground: Color(0xFFE8F5EA),
    card: Color(0xFF0D1F10),
    cardForeground: Color(0xFFE8F5EA),
    primary: Color(0xFF86D0AF),
    primaryForeground: Color(0xFF08160A),
    secondary: Color(0xFF2C6D34),
    secondaryForeground: Color(0xFFE8F5EA),
    accent: Color(0xFF42A980),
    accentForeground: Color(0xFF08160A),
    muted: Color(0xFF1A2E1D),
    mutedForeground: Color(0xFFA6B8A8),
    border: Color(0xFF5F7F63),
    // Derived `129 26% 18%`: one step above `muted`, decorative separators only
    // (mirrors light `borderSubtle`, which is also below the 3:1 non-text minimum).
    borderSubtle: Color(0xFF223A26),
    ring: Color(0xFF86D0AF),
    destructive: Color(0xFFFF9CA7),
    destructiveForeground: Color(0xFF08160A),
    success: Color(0xFF78DDAA),
    warning: Color(0xFFFFD48A),
  );

  static KarmiColors of(BuildContext context) =>
      Theme.of(context).extension<KarmiColors>()!;

  @override
  KarmiColors copyWith({
    Color? background,
    Color? foreground,
    Color? card,
    Color? cardForeground,
    Color? primary,
    Color? primaryForeground,
    Color? secondary,
    Color? secondaryForeground,
    Color? accent,
    Color? accentForeground,
    Color? muted,
    Color? mutedForeground,
    Color? border,
    Color? borderSubtle,
    Color? ring,
    Color? destructive,
    Color? destructiveForeground,
    Color? success,
    Color? warning,
  }) {
    return KarmiColors(
      background: background ?? this.background,
      foreground: foreground ?? this.foreground,
      card: card ?? this.card,
      cardForeground: cardForeground ?? this.cardForeground,
      primary: primary ?? this.primary,
      primaryForeground: primaryForeground ?? this.primaryForeground,
      secondary: secondary ?? this.secondary,
      secondaryForeground: secondaryForeground ?? this.secondaryForeground,
      accent: accent ?? this.accent,
      accentForeground: accentForeground ?? this.accentForeground,
      muted: muted ?? this.muted,
      mutedForeground: mutedForeground ?? this.mutedForeground,
      border: border ?? this.border,
      borderSubtle: borderSubtle ?? this.borderSubtle,
      ring: ring ?? this.ring,
      destructive: destructive ?? this.destructive,
      destructiveForeground:
          destructiveForeground ?? this.destructiveForeground,
      success: success ?? this.success,
      warning: warning ?? this.warning,
    );
  }

  @override
  KarmiColors lerp(ThemeExtension<KarmiColors>? other, double t) {
    if (other is! KarmiColors) return this;
    Color l(Color a, Color b) => Color.lerp(a, b, t)!;
    return KarmiColors(
      background: l(background, other.background),
      foreground: l(foreground, other.foreground),
      card: l(card, other.card),
      cardForeground: l(cardForeground, other.cardForeground),
      primary: l(primary, other.primary),
      primaryForeground: l(primaryForeground, other.primaryForeground),
      secondary: l(secondary, other.secondary),
      secondaryForeground: l(secondaryForeground, other.secondaryForeground),
      accent: l(accent, other.accent),
      accentForeground: l(accentForeground, other.accentForeground),
      muted: l(muted, other.muted),
      mutedForeground: l(mutedForeground, other.mutedForeground),
      border: l(border, other.border),
      borderSubtle: l(borderSubtle, other.borderSubtle),
      ring: l(ring, other.ring),
      destructive: l(destructive, other.destructive),
      destructiveForeground: l(
        destructiveForeground,
        other.destructiveForeground,
      ),
      success: l(success, other.success),
      warning: l(warning, other.warning),
    );
  }
}
