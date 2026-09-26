import 'package:flutter/material.dart';

class KarmiColors extends ThemeExtension<KarmiColors> {
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
  });

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
    borderSubtle: Color(0x00000000), // Transparent / unassigned in dark mode
    ring: Color(0xFF86D0AF),
    destructive: Color(0xFFFF9CA7),
    destructiveForeground: Color(0xFF08160A),
  );

  @override
  ThemeExtension<KarmiColors> copyWith({
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
    );
  }

  @override
  ThemeExtension<KarmiColors> lerp(
      ThemeExtension<KarmiColors>? other, double t) {
    if (other is! KarmiColors) return this;
    return KarmiColors(
      background: Color.lerp(background, other.background, t)!,
      foreground: Color.lerp(foreground, other.foreground, t)!,
      card: Color.lerp(card, other.card, t)!,
      cardForeground: Color.lerp(cardForeground, other.cardForeground, t)!,
      primary: Color.lerp(primary, other.primary, t)!,
      primaryForeground:
          Color.lerp(primaryForeground, other.primaryForeground, t)!,
      secondary: Color.lerp(secondary, other.secondary, t)!,
      secondaryForeground:
          Color.lerp(secondaryForeground, other.secondaryForeground, t)!,
      accent: Color.lerp(accent, other.accent, t)!,
      accentForeground:
          Color.lerp(accentForeground, other.accentForeground, t)!,
      muted: Color.lerp(muted, other.muted, t)!,
      mutedForeground: Color.lerp(mutedForeground, other.mutedForeground, t)!,
      border: Color.lerp(border, other.border, t)!,
      borderSubtle: Color.lerp(borderSubtle, other.borderSubtle, t)!,
      ring: Color.lerp(ring, other.ring, t)!,
      destructive: Color.lerp(destructive, other.destructive, t)!,
      destructiveForeground:
          Color.lerp(destructiveForeground, other.destructiveForeground, t)!,
    );
  }
}
