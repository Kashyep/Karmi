import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';

/// Karmi loading motif: three pulsing dots in the tier accent colour,
/// with an optional live-region status label beside them.
///
/// Under reduced motion ([KarmiAccessibility.reduceMotionOf]), the animation
/// controller stops and the dots are rendered statically without scheduling tickers.
///
/// To prevent rebuilding parent widgets or the message transcript on every animation
/// frame, the animation is self-contained with its own [AnimationController] and
/// wrapped in a [RepaintBoundary].
class KarmiTypingDots extends StatefulWidget {
  const KarmiTypingDots({
    super.key,
    this.label,
    this.color,
    this.dotSize = 5.0,
    this.spacing = 4.0,
  });

  /// Status label displayed beside the dots (e.g., 'Working…').
  final String? label;

  /// Custom dot colour. If null, defaults to the active tier's primary accent.
  final Color? color;

  /// Base diameter of each dot.
  final double dotSize;

  /// Horizontal spacing between dots.
  final double spacing;

  @override
  State<KarmiTypingDots> createState() => _KarmiTypingDotsState();
}

class _KarmiTypingDotsState extends State<KarmiTypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  bool _reducedMotion = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = KarmiAccessibility.reduceMotionOf(context);
    _reducedMotion = reduce;
    if (reduce) {
      if (_controller.isAnimating) {
        _controller.stop();
      }
    } else {
      if (!_controller.isAnimating) {
        _controller.repeat();
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>();
    final dotColor =
        widget.color ??
        colors?.primary ??
        Theme.of(context).colorScheme.primary;

    Widget dots;
    if (_reducedMotion) {
      dots = SizedBox(
        width: widget.dotSize * 3 + widget.spacing * 2,
        height: widget.dotSize * 1.5,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            for (var i = 0; i < 3; i++) ...[
              if (i > 0) SizedBox(width: widget.spacing),
              Container(
                width: widget.dotSize,
                height: widget.dotSize,
                decoration: BoxDecoration(
                  color: dotColor.withValues(alpha: 0.8),
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ],
        ),
      );
    } else {
      dots = RepaintBoundary(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) {
            return CustomPaint(
              size: Size(
                widget.dotSize * 3 + widget.spacing * 2,
                widget.dotSize * 1.5,
              ),
              painter: _TypingDotsPainter(
                progress: _controller.value,
                color: dotColor,
                dotSize: widget.dotSize,
                spacing: widget.spacing,
              ),
            );
          },
        ),
      );
    }

    final effectiveLabel = widget.label;
    final textStyle = Theme.of(
      context,
    ).textTheme.bodyMedium?.copyWith(color: colors?.mutedForeground);

    final content = Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        dots,
        if (effectiveLabel != null && effectiveLabel.isNotEmpty) ...[
          const SizedBox(width: 8),
          Flexible(child: Text(effectiveLabel, style: textStyle)),
        ],
      ],
    );

    return Semantics(
      liveRegion: true,
      label: effectiveLabel ?? 'Working…',
      excludeSemantics: true,
      child: content,
    );
  }
}

class _TypingDotsPainter extends CustomPainter {
  _TypingDotsPainter({
    required this.progress,
    required this.color,
    required this.dotSize,
    required this.spacing,
  });

  final double progress;
  final Color color;
  final double dotSize;
  final double spacing;

  @override
  void paint(Canvas canvas, Size size) {
    final centerY = size.height / 2;
    final radius = dotSize / 2;

    for (var i = 0; i < 3; i++) {
      final offset = (progress - (i * 0.18)) % 1.0;
      final normalized = offset < 0 ? offset + 1.0 : offset;

      double wave = 0.0;
      if (normalized <= 0.5) {
        wave = math.sin(normalized / 0.5 * math.pi);
      }

      final scale = 0.75 + 0.4 * wave;
      final opacity = (0.35 + 0.65 * wave).clamp(0.0, 1.0);

      final dotCenterX = radius + i * (dotSize + spacing);
      final paint = Paint()
        ..color = color.withValues(alpha: opacity)
        ..style = PaintingStyle.fill;

      canvas.drawCircle(Offset(dotCenterX, centerY), radius * scale, paint);
    }
  }

  @override
  bool shouldRepaint(_TypingDotsPainter oldDelegate) =>
      oldDelegate.progress != progress ||
      oldDelegate.color != color ||
      oldDelegate.dotSize != dotSize ||
      oldDelegate.spacing != spacing;
}
