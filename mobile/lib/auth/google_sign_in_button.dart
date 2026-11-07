import 'package:flutter/material.dart';

/// Official Google "G" logo vector painter according to Google Identity Branding Guidelines.
class GoogleLogoPainter extends CustomPainter {
  const GoogleLogoPainter();

  @override
  void paint(Canvas canvas, Size size) {
    // Vector viewBox: 0 0 14 14
    final scale = size.shortestSide / 14.0;
    canvas.save();
    canvas.scale(scale, scale);

    final paint = Paint()..style = PaintingStyle.fill;

    // Blue (#4285F4)
    paint.color = const Color(0xFF4285F4);
    final bluePath = Path()
      ..moveTo(13.499, 7.14597)
      ..cubicTo(13.499, 6.69497, 13.463, 6.24097, 13.385, 5.79797)
      ..lineTo(7.12903, 5.79797)
      ..lineTo(7.12903, 8.35196)
      ..lineTo(10.711, 8.35196)
      ..cubicTo(10.563, 9.17596, 10.085, 9.90397, 9.38602, 10.367)
      ..lineTo(9.38602, 12.024)
      ..lineTo(11.523, 12.024)
      ..cubicTo(12.778, 10.869, 13.499, 9.16297, 13.499, 7.14597)
      ..close();
    canvas.drawPath(bluePath, paint);

    // Green (#34A853)
    paint.color = const Color(0xFF34A853);
    final greenPath = Path()
      ..moveTo(7.13, 13.628)
      ..cubicTo(8.919, 13.628, 10.427, 13.041, 11.526, 12.027)
      ..lineTo(9.38901, 10.37)
      ..cubicTo(8.79401, 10.774, 8.02699, 11.003, 7.13199, 11.003)
      ..cubicTo(5.40199, 11.003, 3.935, 9.83597, 3.409, 8.26697)
      ..lineTo(1.203, 8.26697)
      ..lineTo(1.203, 9.97498)
      ..cubicTo(2.329, 12.215, 4.622, 13.628, 7.13, 13.628)
      ..close();
    canvas.drawPath(greenPath, paint);

    // Yellow (#FBBC04 / #FBBC05)
    paint.color = const Color(0xFFFBBC04);
    final yellowPath = Path()
      ..moveTo(3.409, 8.26398)
      ..cubicTo(3.131, 7.44098, 3.131, 6.54898, 3.409, 5.72498)
      ..lineTo(3.409, 4.01697)
      ..lineTo(1.20599, 4.01697)
      ..cubicTo(0.264994, 5.89097, 0.264994, 8.09896, 1.20599, 9.97296)
      ..lineTo(3.409, 8.26398)
      ..close();
    canvas.drawPath(yellowPath, paint);

    // Red (#EA4335)
    paint.color = const Color(0xFFEA4335);
    final redPath = Path()
      ..moveTo(7.13, 2.98506)
      ..cubicTo(8.076, 2.97106, 8.98901, 3.32708, 9.67401, 3.98008)
      ..lineTo(11.568, 2.08607)
      ..cubicTo(10.369, 0.960072, 8.777, 0.341066, 7.13, 0.361066)
      ..cubicTo(4.622, 0.361066, 2.329, 1.77406, 1.203, 4.01606)
      ..lineTo(3.40601, 5.72508)
      ..cubicTo(3.93001, 4.15308, 5.4, 2.98506, 7.13, 2.98506)
      ..close();
    canvas.drawPath(redPath, paint);

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// A "Continue with Google" button conforming to Google Identity Branding Guidelines.
///
/// Supports light and dark theme variants, 48 dp minimum height, accessible semantics,
/// and idle / loading / disabled states.
class GoogleSignInButton extends StatelessWidget {
  const GoogleSignInButton({
    super.key,
    required this.onPressed,
    this.isLoading = false,
  });

  final VoidCallback? onPressed;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark ? const Color(0xFF131314) : Colors.white;
    final textColor = isDark
        ? const Color(0xFFE3E3E3)
        : const Color(0xFF1F1F1F);
    final borderColor = isDark
        ? const Color(0xFF8E918F)
        : const Color(0xFF747775);

    final isInteractive = onPressed != null && !isLoading;

    return Semantics(
      label: 'Continue with Google',
      button: true,
      enabled: isInteractive,
      excludeSemantics: true,
      child: Material(
        color: backgroundColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: borderColor, width: 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: isInteractive ? onPressed : null,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 48),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (isLoading)
                    SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(textColor),
                      ),
                    )
                  else
                    const SizedBox(
                      width: 20,
                      height: 20,
                      child: CustomPaint(painter: GoogleLogoPainter()),
                    ),
                  const SizedBox(width: 12),
                  Flexible(
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        'Continue with Google',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: textColor,
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
