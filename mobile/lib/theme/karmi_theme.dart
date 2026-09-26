import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'karmi_colors.dart';

/// The only place that calls `GoogleFonts.*` (UI_IMPLEMENTATION_PLAN.md §3.2 step 5).
///
/// google_fonts replaces `fontFamilyFallback` with its own family name, so the
/// Devanagari fallback is re-applied after each call (§3.4).
abstract final class KarmiTypography {
  static const sansFallback = <String>['Noto Sans Devanagari'];
  static const serifFallback = <String>['Noto Serif Devanagari'];

  static TextStyle _exo(FontWeight weight, double size, double height) =>
      GoogleFonts.exo(
        fontWeight: weight,
        fontSize: size,
        height: height,
      ).copyWith(fontFamilyFallback: sansFallback);

  static TextStyle _proza(
    FontWeight weight,
    double size,
    double height, {
    FontStyle style = FontStyle.normal,
  }) => GoogleFonts.prozaLibre(
    fontWeight: weight,
    fontStyle: style,
    fontSize: size,
    height: height,
  ).copyWith(fontFamilyFallback: sansFallback);

  /// §3.5 type scale. Colours are applied by [KarmiTheme].
  static TextTheme textTheme() => TextTheme(
    displaySmall: _exo(FontWeight.w700, 32, 1.25),
    headlineSmall: _exo(FontWeight.w600, 24, 1.33),
    titleLarge: _exo(FontWeight.w600, 20, 1.4),
    titleMedium: _exo(FontWeight.w600, 16, 1.5),
    labelLarge: _proza(FontWeight.w600, 14, 1.43),
    labelMedium: _exo(FontWeight.w500, 13, 1.3),
    bodyLarge: _proza(FontWeight.w400, 16, 1.55),
    bodyMedium: _proza(FontWeight.w400, 14, 1.5),
    labelSmall: _proza(FontWeight.w600, 13, 1.38),
  );

  /// Trykker has no italic; never set [FontStyle.italic] on it (§3.3).
  static TextStyle quote() => GoogleFonts.trykker(
    fontWeight: FontWeight.w400,
    fontSize: 18,
    height: 1.55,
  ).copyWith(fontFamilyFallback: serifFallback);

  /// Proza Libre 400 italic, for helper/aside text.
  static TextStyle emphasis() =>
      _proza(FontWeight.w400, 16, 1.55, style: FontStyle.italic);
}

/// Styles outside the M3 slots.
@immutable
class KarmiText extends ThemeExtension<KarmiText> {
  const KarmiText({required this.quote, required this.emphasis});

  /// Trykker accent callouts only (EmptyState, Welcome tagline).
  final TextStyle quote;
  final TextStyle emphasis;

  static KarmiText of(BuildContext context) =>
      Theme.of(context).extension<KarmiText>()!;

  @override
  KarmiText copyWith({TextStyle? quote, TextStyle? emphasis}) => KarmiText(
    quote: quote ?? this.quote,
    emphasis: emphasis ?? this.emphasis,
  );

  @override
  KarmiText lerp(ThemeExtension<KarmiText>? other, double t) {
    if (other is! KarmiText) return this;
    return KarmiText(
      quote: TextStyle.lerp(quote, other.quote, t)!,
      emphasis: TextStyle.lerp(emphasis, other.emphasis, t)!,
    );
  }
}

/// Non-colour tokens: radii and the focus ring (2px, 3px under high contrast; §5.2).
@immutable
class KarmiShape extends ThemeExtension<KarmiShape> {
  const KarmiShape({required this.focusRingWidth, required this.highContrast});

  static const controlRadius = 10.0;
  static const cardRadius = 14.0;
  static const minTapTarget = 48.0;

  final double focusRingWidth;
  final bool highContrast;

  static KarmiShape of(BuildContext context) =>
      Theme.of(context).extension<KarmiShape>()!;

  @override
  KarmiShape copyWith({double? focusRingWidth, bool? highContrast}) =>
      KarmiShape(
        focusRingWidth: focusRingWidth ?? this.focusRingWidth,
        highContrast: highContrast ?? this.highContrast,
      );

  @override
  KarmiShape lerp(ThemeExtension<KarmiShape>? other, double t) =>
      other is KarmiShape && t >= 0.5 ? other : this;
}

abstract final class KarmiTheme {
  static ThemeData get light => build(Brightness.light);
  static ThemeData get dark => build(Brightness.dark);
  static ThemeData get highContrastLight =>
      build(Brightness.light, highContrast: true);
  static ThemeData get highContrastDark =>
      build(Brightness.dark, highContrast: true);

  /// With [highContrast], every border uses the foreground colour and focus
  /// rings grow to 3px (UI_IMPLEMENTATION_PLAN.md §5.2).
  static ThemeData build(Brightness brightness, {bool highContrast = false}) {
    final base = brightness == Brightness.light
        ? KarmiColors.light
        : KarmiColors.dark;
    final colors = highContrast
        ? base.copyWith(border: base.foreground, borderSubtle: base.foreground)
        : base;
    final shape = KarmiShape(
      focusRingWidth: highContrast ? 3 : 2,
      highContrast: highContrast,
    );
    final ring = BorderSide(color: colors.ring, width: shape.focusRingWidth);
    final outline = BorderSide(color: colors.border);
    final cardSide = BorderSide(color: colors.borderSubtle);

    final scheme = ColorScheme(
      brightness: brightness,
      primary: colors.primary,
      onPrimary: colors.primaryForeground,
      primaryContainer: colors.muted,
      onPrimaryContainer: colors.foreground,
      secondary: colors.secondary,
      onSecondary: colors.secondaryForeground,
      secondaryContainer: colors.secondary,
      onSecondaryContainer: colors.secondaryForeground,
      tertiary: colors.accent,
      onTertiary: colors.accentForeground,
      error: colors.destructive,
      onError: colors.destructiveForeground,
      surface: colors.card,
      onSurface: colors.foreground,
      onSurfaceVariant: colors.mutedForeground,
      surfaceContainerLowest: colors.card,
      surfaceContainerLow: colors.card,
      surfaceContainer: colors.card,
      surfaceContainerHigh: colors.muted,
      surfaceContainerHighest: colors.muted,
      outline: colors.border,
      outlineVariant: colors.borderSubtle,
      surfaceTint: Colors.transparent,
      shadow: Colors.black,
      scrim: Colors.black,
      inverseSurface: colors.foreground,
      onInverseSurface: colors.background,
      inversePrimary: brightness == Brightness.light
          ? KarmiColors.dark.primary
          : KarmiColors.light.primary,
    );

    final text = KarmiTypography.textTheme().apply(
      bodyColor: colors.foreground,
      displayColor: colors.foreground,
    );

    WidgetStateProperty<BorderSide?> focusSide(BorderSide? idle) =>
        WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.focused) ? ring : idle,
        );

    const minSize = Size(KarmiShape.minTapTarget, KarmiShape.minTapTarget);
    final controlShape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(KarmiShape.controlRadius),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: colors.background,
      canvasColor: colors.background,
      textTheme: text,
      focusColor: colors.ring.withValues(alpha: 0.16),
      materialTapTargetSize: MaterialTapTargetSize.padded,
      extensions: [
        colors,
        shape,
        KarmiText(
          quote: KarmiTypography.quote().copyWith(color: colors.foreground),
          emphasis: KarmiTypography.emphasis().copyWith(
            color: colors.mutedForeground,
          ),
        ),
      ],
      filledButtonTheme: FilledButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(minSize),
          shape: WidgetStatePropertyAll(controlShape),
          textStyle: WidgetStatePropertyAll(text.labelLarge),
          // --ring equals the --primary fill, so a filled button's focus ring
          // is an inset ring in --primary-foreground (5.97:1 light, 10.32:1 dark).
          side: WidgetStateProperty.resolveWith(
            (states) => states.contains(WidgetState.focused)
                ? BorderSide(
                    color: colors.primaryForeground,
                    width: shape.focusRingWidth,
                  )
                : null,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(minSize),
          shape: WidgetStatePropertyAll(controlShape),
          textStyle: WidgetStatePropertyAll(text.labelLarge),
          foregroundColor: WidgetStatePropertyAll(colors.foreground),
          side: focusSide(outline),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(minSize),
          shape: WidgetStatePropertyAll(controlShape),
          textStyle: WidgetStatePropertyAll(text.labelLarge),
          side: focusSide(null),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(minSize),
          side: focusSide(null),
        ),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(minSize),
          textStyle: WidgetStatePropertyAll(text.labelLarge),
          side: focusSide(outline),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.card,
        hintStyle: text.bodyLarge?.copyWith(color: colors.mutedForeground),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 12,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(KarmiShape.controlRadius),
          borderSide: outline,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(KarmiShape.controlRadius),
          borderSide: outline,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(KarmiShape.controlRadius),
          borderSide: ring,
        ),
      ),
      cardTheme: CardThemeData(
        color: colors.card,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(KarmiShape.cardRadius),
          side: cardSide,
        ),
      ),
      dividerTheme: DividerThemeData(color: colors.borderSubtle, thickness: 1),
      listTileTheme: ListTileThemeData(
        minVerticalPadding: 12,
        titleTextStyle: text.bodyLarge,
        subtitleTextStyle: text.bodyMedium?.copyWith(
          color: colors.mutedForeground,
        ),
        iconColor: colors.foreground,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: colors.card,
        foregroundColor: colors.foreground,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: text.titleMedium,
        shape: Border(bottom: cardSide),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: colors.card,
        indicatorColor: colors.secondary,
        labelTextStyle: WidgetStatePropertyAll(text.labelMedium),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            color: states.contains(WidgetState.selected)
                ? colors.secondaryForeground
                : colors.foreground,
          ),
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: colors.card,
        modalBackgroundColor: colors.card,
        showDragHandle: true,
      ),
      dialogTheme: DialogThemeData(backgroundColor: colors.card),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: colors.foreground,
        contentTextStyle: text.bodyMedium?.copyWith(color: colors.background),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: colors.primary,
        linearTrackColor: colors.muted,
      ),
    );
  }
}
