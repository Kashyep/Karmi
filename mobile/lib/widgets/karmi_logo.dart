import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';

/// Karmi's own mark: a rounded squircle with a stylised "K" cut out of the
/// primary colour.
///
/// The app never shows a model or provider name to the user, so this mark is
/// used wherever that identity used to appear (reply header, tester metadata
/// line). It is drawn in code, so there is no image asset to keep in sync and
/// it scales cleanly at any size.
class KarmiLogo extends StatelessWidget {
  const KarmiLogo({
    super.key,
    this.size = 24,
    this.background,
    this.mark,
    this.semanticLabel = 'Karmi',
  });

  /// Edge length of the square mark.
  final double size;

  /// Squircle fill. Defaults to the theme primary colour.
  final Color? background;

  /// Colour of the "K". Defaults to the theme primary foreground.
  final Color? mark;

  /// Screen-reader label; set to null to omit the mark from the a11y tree.
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final painter = _KarmiMarkPainter(
      background: background ?? colors.primary,
      mark: mark ?? colors.primaryForeground,
    );
    final logo = SizedBox(
      width: size,
      height: size,
      child: CustomPaint(painter: painter),
    );
    if (semanticLabel == null) {
      return ExcludeSemantics(child: logo);
    }
    return Semantics(label: semanticLabel, image: true, child: logo);
  }
}

class _KarmiMarkPainter extends CustomPainter {
  const _KarmiMarkPainter({required this.background, required this.mark});

  final Color background;
  final Color mark;

  @override
  void paint(Canvas canvas, Size size) {
    final side = size.shortestSide;
    final radius = Radius.circular(side * 0.3);
    final squircle = RRect.fromRectAndRadius(
      Rect.fromLTWH(0, 0, side, side),
      radius,
    );
    canvas.drawRRect(squircle, Paint()..color = background);

    final stroke = side * 0.1;
    final paint = Paint()
      ..color = mark
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;

    final path = Path()
      // Vertical stem of the K.
      ..moveTo(side * 0.34, side * 0.26)
      ..lineTo(side * 0.34, side * 0.74)
      // Upper arm.
      ..moveTo(side * 0.68, side * 0.26)
      ..lineTo(side * 0.36, side * 0.5)
      // Lower leg.
      ..moveTo(side * 0.45, side * 0.44)
      ..lineTo(side * 0.7, side * 0.74);
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_KarmiMarkPainter oldDelegate) =>
      oldDelegate.background != background || oldDelegate.mark != mark;
}
