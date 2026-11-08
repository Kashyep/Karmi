import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';

/// Small rounded pill displaying an inline citation index.
class CitationChip extends StatelessWidget {
  const CitationChip({super.key, required this.index});

  final int index;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    final backgroundColor = colors?.secondary ?? colorScheme.primaryContainer;
    final textColor =
        colors?.secondaryForeground ?? colorScheme.onPrimaryContainer;
    final borderColor = colors?.borderSubtle ?? colorScheme.outlineVariant;

    final labelStyle = (textTheme.labelSmall ?? const TextStyle()).copyWith(
      color: textColor,
      fontWeight: FontWeight.w600,
    );

    return Semantics(
      container: true,
      button: false,
      label: 'Citation $index',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        margin: const EdgeInsets.symmetric(horizontal: 2),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: borderColor, width: 0.5),
        ),
        child: Text('[$index]', style: labelStyle),
      ),
    );
  }
}
