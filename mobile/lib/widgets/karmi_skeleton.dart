import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';

/// A single skeleton placeholder element with an optional subtle pulse shimmer.
///
/// Under reduced motion ([KarmiAccessibility.reduceMotionOf]), the animation
/// controller stops and the skeleton is drawn statically without scheduling tickers.
///
/// Wrapped in [RepaintBoundary] with internal animation via [AnimatedBuilder].
class KarmiSkeleton extends StatefulWidget {
  const KarmiSkeleton({
    super.key,
    this.width,
    this.height,
    this.borderRadius,
    this.color,
  });

  final double? width;
  final double? height;
  final BorderRadius? borderRadius;
  final Color? color;

  @override
  State<KarmiSkeleton> createState() => _KarmiSkeletonState();
}

class _KarmiSkeletonState extends State<KarmiSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  bool _reducedMotion = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
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
        _controller.repeat(reverse: true);
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
    final baseColor =
        widget.color ??
        (colors != null
            ? (colors.brightness == Brightness.dark
                  ? Colors.white
                  : Colors.black)
            : Theme.of(context).colorScheme.onSurface);

    final radius = widget.borderRadius ?? BorderRadius.circular(4);

    if (_reducedMotion) {
      return Container(
        width: widget.width,
        height: widget.height,
        decoration: BoxDecoration(
          color: baseColor.withValues(alpha: 0.1),
          borderRadius: radius,
        ),
      );
    }

    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          final alpha = 0.08 + 0.12 * _controller.value;
          return Container(
            width: widget.width,
            height: widget.height,
            decoration: BoxDecoration(
              color: baseColor.withValues(alpha: alpha),
              borderRadius: radius,
            ),
          );
        },
      ),
    );
  }
}

/// A skeleton placeholder row representing a conversation item in the history list.
class KarmiHistorySkeletonRow extends StatelessWidget {
  const KarmiHistorySkeletonRow({super.key, this.widthFactor = 0.7});

  final double widthFactor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            FractionallySizedBox(
              widthFactor: widthFactor,
              child: const KarmiSkeleton(
                height: 14,
                borderRadius: BorderRadius.all(Radius.circular(4)),
              ),
            ),
            const SizedBox(height: 8),
            const KarmiSkeleton(
              width: 60,
              height: 10,
              borderRadius: BorderRadius.all(Radius.circular(3)),
            ),
          ],
        ),
      ),
    );
  }
}

/// A list of skeleton rows displayed while the conversation history list is loading.
class KarmiHistorySkeletonList extends StatelessWidget {
  const KarmiHistorySkeletonList({super.key, this.count = 6});

  final int count;

  @override
  Widget build(BuildContext context) {
    final factors = [0.75, 0.55, 0.85, 0.65, 0.45, 0.7];
    return ListView.builder(
      physics: const NeverScrollableScrollPhysics(),
      shrinkWrap: true,
      itemCount: count,
      itemBuilder: (context, index) {
        return KarmiHistorySkeletonRow(
          widthFactor: factors[index % factors.length],
        );
      },
    );
  }
}

/// Skeleton rows representing message turns shown while conversation messages load.
class KarmiMessageHistorySkeleton extends StatelessWidget {
  const KarmiMessageHistorySkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          Align(
            alignment: Alignment.centerRight,
            child: KarmiSkeleton(
              width: 180,
              height: 40,
              borderRadius: BorderRadius.all(Radius.circular(16)),
            ),
          ),
          SizedBox(height: 16),
          Align(
            alignment: Alignment.centerLeft,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                KarmiSkeleton(
                  width: 240,
                  height: 16,
                  borderRadius: BorderRadius.all(Radius.circular(4)),
                ),
                SizedBox(height: 8),
                KarmiSkeleton(
                  width: 200,
                  height: 16,
                  borderRadius: BorderRadius.all(Radius.circular(4)),
                ),
                SizedBox(height: 8),
                KarmiSkeleton(
                  width: 140,
                  height: 16,
                  borderRadius: BorderRadius.all(Radius.circular(4)),
                ),
              ],
            ),
          ),
          SizedBox(height: 24),
          Align(
            alignment: Alignment.centerRight,
            child: KarmiSkeleton(
              width: 140,
              height: 36,
              borderRadius: BorderRadius.all(Radius.circular(16)),
            ),
          ),
          SizedBox(height: 16),
          Align(
            alignment: Alignment.centerLeft,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                KarmiSkeleton(
                  width: 260,
                  height: 16,
                  borderRadius: BorderRadius.all(Radius.circular(4)),
                ),
                SizedBox(height: 8),
                KarmiSkeleton(
                  width: 180,
                  height: 16,
                  borderRadius: BorderRadius.all(Radius.circular(4)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
