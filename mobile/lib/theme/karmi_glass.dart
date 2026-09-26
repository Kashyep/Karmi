import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'karmi_colors.dart';
import 'karmi_motion.dart';
import 'karmi_theme.dart';

/// Glass configuration and the opaque fallback (UI_IMPLEMENTATION_PLAN.md §5).
///
/// Glass is only used on the §5.1 surfaces: app bar, tab bar, composer tray,
/// settings header and menus. Everything else is an opaque `KarmiCard`.
abstract final class KarmiGlass {
  /// Legibility floor: tint alpha ≥ 0.72 light, ≥ 0.78 dark (§5.1).
  static const lightTintAlpha = 0.72;
  static const darkTintAlpha = 0.78;

  /// Both variants are populated; `GlassTheme.brightnessOf` picks one per
  /// context from the Material theme (`brightnessResolver`).
  static GlassThemeData themeData() => GlassThemeData(
    light: _variant(GlassThemeVariant.light, KarmiColors.light, lightTintAlpha),
    dark: _variant(GlassThemeVariant.dark, KarmiColors.dark, darkTintAlpha),
  );

  static GlassThemeVariant _variant(
    GlassThemeVariant base,
    KarmiColors colors,
    double alpha,
  ) {
    final tint = colors.card.withValues(alpha: alpha);
    return base.copyWith(
      settings: (base.settings ?? const GlassThemeSettings()).copyWith(
        glassColor: tint,
      ),
    );
  }
}

/// A glass platter that becomes an opaque `--card` surface with a 1px `--border`
/// stroke when reduce transparency (or platform high contrast) is on (§5.2).
class KarmiGlassSurface extends StatelessWidget {
  const KarmiGlassSurface({
    super.key,
    required this.child,
    this.padding,
    this.radius = KarmiShape.cardRadius,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final double radius;

  @override
  Widget build(BuildContext context) {
    if (KarmiAccessibility.reduceTransparencyOf(context)) {
      final colors = KarmiColors.of(context);
      return DecoratedBox(
        key: const ValueKey('karmi-glass-opaque'),
        decoration: BoxDecoration(
          color: colors.card,
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(color: colors.border),
        ),
        child: Padding(padding: padding ?? EdgeInsets.zero, child: child),
      );
    }
    return GlassContainer(
      key: const ValueKey('karmi-glass'),
      padding: padding,
      shape: LiquidRoundedSuperellipse(borderRadius: radius),
      child: child,
    );
  }
}
