import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'karmi_colors.dart';

class KarmiTypography {
  static const fallbackStack = ['Noto Sans Devanagari'];
  static const trykkerFallback = ['Noto Serif Devanagari'];

  static TextTheme createTextTheme(Color textColor) {
    return TextTheme(
      displaySmall: GoogleFonts.exo(
        fontWeight: FontWeight.w700,
        fontSize: 32,
        height: 1.25,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      headlineSmall: GoogleFonts.exo(
        fontWeight: FontWeight.w600,
        fontSize: 24,
        height: 1.33,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      titleLarge: GoogleFonts.exo(
        fontWeight: FontWeight.w600,
        fontSize: 20,
        height: 1.4,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      titleMedium: GoogleFonts.exo(
        fontWeight: FontWeight.w600,
        fontSize: 16,
        height: 1.5,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      labelLarge: GoogleFonts.prozaLibre(
        fontWeight: FontWeight.w600,
        fontSize: 14,
        height: 1.43,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      labelMedium: GoogleFonts.exo(
        fontWeight: FontWeight.w500,
        fontSize: 13,
        height: 1.3,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      bodyLarge: GoogleFonts.prozaLibre(
        fontWeight: FontWeight.w400,
        fontSize: 16,
        height: 1.55,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      bodyMedium: GoogleFonts.prozaLibre(
        fontWeight: FontWeight.w400,
        fontSize: 14,
        height: 1.5,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
      labelSmall: GoogleFonts.prozaLibre(
        fontWeight: FontWeight.w600,
        fontSize: 13,
        height: 1.38,
        color: textColor,
        textStyle: const TextStyle(fontFamilyFallback: fallbackStack),
      ),
    );
  }

  static TextStyle get quoteStyle {
    return GoogleFonts.trykker(
      fontWeight: FontWeight.w400,
      fontSize: 18,
      height: 1.55,
      textStyle: const TextStyle(fontFamilyFallback: trykkerFallback),
    );
  }
}

class KarmiTheme {
  static ThemeData get light {
    final colors = KarmiColors.light;
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.light(
        primary: colors.primary,
        onPrimary: colors.primaryForeground,
        secondary: colors.secondary,
        onSecondary: colors.secondaryForeground,
        error: colors.destructive,
        onError: colors.destructiveForeground,
        surface: colors.background,
        onSurface: colors.foreground,
      ),
      scaffoldBackgroundColor: colors.background,
      extensions: [colors],
      textTheme: KarmiTypography.createTextTheme(colors.foreground),
    );
  }

  static ThemeData get dark {
    final colors = KarmiColors.dark;
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.dark(
        primary: colors.primary,
        onPrimary: colors.primaryForeground,
        secondary: colors.secondary,
        onSecondary: colors.secondaryForeground,
        error: colors.destructive,
        onError: colors.destructiveForeground,
        surface: colors.background,
        onSurface: colors.foreground,
      ),
      scaffoldBackgroundColor: colors.background,
      extensions: [colors],
      textTheme: KarmiTypography.createTextTheme(colors.foreground),
    );
  }
}
