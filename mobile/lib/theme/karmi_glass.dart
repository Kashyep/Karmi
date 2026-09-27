import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'karmi_colors.dart';
import 'karmi_motion.dart';
import 'karmi_theme.dart';
import 'karmi_tier.dart';

/// Liquid Glass configuration and primitives (implementation_plan.md §1.3,
/// UI_IMPLEMENTATION_PLAN.md §5).
///
/// Glass is only used on floating chrome: app bar, tab bar, composer tray,
/// settings header and the Armory preview banner. Content stays on opaque
/// `KarmiCard`s. The tint is the tier's `glassBase` token: `--card` tinted
/// towards the tier's Primary Base, at the legibility-floor alpha (0.72 light,
/// 0.78 dark), which the token audit proves keeps text ≥4.5:1 over worst-case
/// backdrops.
abstract final class KarmiGlass {
  /// Legibility floor: tint alpha ≥ 0.72 light, ≥ 0.78 dark (§5.1).
  static const lightTintAlpha = 0.72;
  static const darkTintAlpha = 0.78;

  /// Both brightness variants for [tier]; `GlassTheme.brightnessOf` picks one
  /// per context from the Material theme (`brightnessResolver`).
  static GlassThemeData themeData(KarmiTier tier) => GlassThemeData(
    light: _variant(GlassThemeVariant.light, tier, Brightness.light),
    dark: _variant(GlassThemeVariant.dark, tier, Brightness.dark),
  );

  /// The tier's frosted tint. Also the platter behind the glass app bar,
  /// which liquid_glass_widgets draws with no fill of its own.
  static Color tint(KarmiTier tier, Brightness brightness) =>
      KarmiColors.forTier(tier, brightness).glassBase;

  static GlassThemeVariant _variant(
    GlassThemeVariant base,
    KarmiTier tier,
    Brightness brightness,
  ) {
    return base.copyWith(
      settings: (base.settings ?? const GlassThemeSettings()).copyWith(
        glassColor: tint(tier, brightness),
      ),
    );
  }
}

/// A glass platter: frosted tier tint, 1px `glassBorder` rim and a top-edge
/// `glassHighlight` (the "lighting"). With [onTap] it becomes interactive and
/// shows hover/pressed feedback.
///
/// Fallback: when reduce transparency (or platform high contrast) is on it is
/// an opaque `--card` surface with a 1px `--border` stroke (§5.2) — the
/// Flutter counterpart of CSS `@supports not (backdrop-filter)`.
class KarmiGlassSurface extends StatefulWidget {
  const KarmiGlassSurface({
    super.key,
    required this.child,
    this.padding,
    this.radius = KarmiShape.cardRadius,
    this.onTap,
    this.semanticLabel,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final double radius;
  final VoidCallback? onTap;
  final String? semanticLabel;

  @override
  State<KarmiGlassSurface> createState() => _KarmiGlassSurfaceState();
}

class _KarmiGlassSurfaceState extends State<KarmiGlassSurface> {
  bool _hovered = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final radius = BorderRadius.circular(widget.radius);
    final content = Padding(
      padding: widget.padding ?? EdgeInsets.zero,
      child: widget.child,
    );

    Widget surface;
    if (KarmiAccessibility.reduceTransparencyOf(context)) {
      surface = DecoratedBox(
        key: const ValueKey('karmi-glass-opaque'),
        decoration: BoxDecoration(
          color: colors.card,
          borderRadius: radius,
          border: Border.all(color: colors.border),
        ),
        child: content,
      );
    } else {
      surface = DecoratedBox(
        key: const ValueKey('karmi-glass-rim'),
        position: DecorationPosition.foreground,
        decoration: BoxDecoration(
          borderRadius: radius,
          border: Border.all(color: colors.glassBorder),
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.center,
            colors: [colors.glassHighlight, colors.glassHighlight.withAlpha(0)],
            stops: const [0, 0.35],
          ),
        ),
        child: GlassContainer(
          key: const ValueKey('karmi-glass'),
          shape: LiquidRoundedSuperellipse(borderRadius: widget.radius),
          child: content,
        ),
      );
    }

    final onTap = widget.onTap;
    if (onTap == null) return surface;

    // Hover lifts the tint towards the foreground, press deepens it.
    final overlay = _pressed
        ? colors.foreground.withValues(alpha: 0.10)
        : _hovered
        ? colors.foreground.withValues(alpha: 0.05)
        : Colors.transparent;
    return Semantics(
      button: true,
      label: widget.semanticLabel,
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hovered = true),
        onExit: (_) => setState(() => _hovered = false),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: (_) => setState(() => _pressed = true),
          onTapCancel: () => setState(() => _pressed = false),
          onTapUp: (_) => setState(() => _pressed = false),
          onTap: onTap,
          child: AnimatedContainer(
            key: const ValueKey('karmi-glass-state'),
            duration: KarmiMotion.duration(context, KarmiMotion.fast),
            foregroundDecoration: BoxDecoration(
              color: overlay,
              borderRadius: radius,
            ),
            child: surface,
          ),
        ),
      ),
    );
  }
}
