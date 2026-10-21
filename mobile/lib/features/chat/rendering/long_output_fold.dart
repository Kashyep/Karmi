import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';

/// Wraps long outputs with a maximum height fold and show more/less toggle.
class LongOutputFold extends StatefulWidget {
  const LongOutputFold({
    super.key,
    required this.child,
    required this.collapsible,
    this.maxHeight = 360,
  });

  final Widget child;
  final bool collapsible;
  final double maxHeight;

  @override
  State<LongOutputFold> createState() => _LongOutputFoldState();
}

class _LongOutputFoldState extends State<LongOutputFold> {
  bool _collapsed = true;

  @override
  Widget build(BuildContext context) {
    if (!widget.collapsible) {
      return widget.child;
    }

    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final surfaceColor = colors?.background ?? colorScheme.surface;

    if (!_collapsed) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          widget.child,
          const SizedBox(height: 4),
          Align(
            alignment: Alignment.center,
            child: TextButton.icon(
              onPressed: () {
                setState(() {
                  _collapsed = true;
                });
              },
              icon: const Icon(Icons.expand_less, size: 18),
              label: const Text('Show less'),
            ),
          ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Stack(
          children: [
            ClipRect(
              child: SizedBox(
                width: double.infinity,
                height: widget.maxHeight,
                child: OverflowBox(
                  alignment: Alignment.topLeft,
                  maxHeight: double.infinity,
                  child: widget.child,
                ),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              height: 72,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      surfaceColor.withValues(alpha: 0.0),
                      surfaceColor,
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
        Align(
          alignment: Alignment.center,
          child: TextButton.icon(
            onPressed: () {
              setState(() {
                _collapsed = false;
              });
            },
            icon: const Icon(Icons.expand_more, size: 18),
            label: const Text('Show more'),
          ),
        ),
      ],
    );
  }
}
