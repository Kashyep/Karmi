import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'karmi_colors.dart';
import 'karmi_motion.dart';

class KarmiGlass {
  static GlassThemeData themeData(BuildContext context,
      {required Brightness brightness}) {
    return GlassThemeData(
      light: GlassThemeVariant(
        settings: GlassThemeSettings(
          glassColor: KarmiColors.light.card.withValues(alpha: 0.72),
        ),
      ),
      dark: GlassThemeVariant(
        settings: GlassThemeSettings(
          glassColor: KarmiColors.dark.card.withValues(alpha: 0.78),
        ),
      ),
    );
  }
}

class KarmiGlassContainer extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final double radius;

  const KarmiGlassContainer({
    super.key,
    required this.child,
    this.padding,
    this.radius = 10.0,
  });

  @override
  Widget build(BuildContext context) {
    final reduceTransparency = KarmiMotion.reduceTransparencyOf(context);
    final colors = Theme.of(context).extension<KarmiColors>()!;

    if (reduceTransparency) {
      return Container(
        padding: padding,
        decoration: BoxDecoration(
          color: colors.card,
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(color: colors.border, width: 1.0),
        ),
        child: child,
      );
    }

    return GlassContainer(
      padding: padding,
      shape: LiquidRoundedSuperellipse(borderRadius: radius),
      child: child,
    );
  }
}
