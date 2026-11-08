import 'package:flutter/material.dart';

import '../theme/karmi_tokens.dart';

/// Warning pill shown when an allowance is near or at its limit.
///
/// Renders nothing below [KarmiTokens.usageWarningThreshold]. At 100% or more
/// it reads "Allowance reached"; otherwise "Near limit". Colours and spacing
/// come from [KarmiTokens] only.
///
/// Accessibility: the pill exposes exactly one labelled semantics node (the
/// label is the visible text); the decorative icon and the text itself are
/// excluded so the label is not announced twice.
class UsageWarningPill extends StatelessWidget {
  const UsageWarningPill({super.key, required this.fraction});

  /// Share of the allowance used, 0.0–1.0 (values above 1.0 are allowed).
  final double fraction;

  @override
  Widget build(BuildContext context) {
    if (!KarmiTokens.isUsageWarning(fraction)) {
      return const SizedBox.shrink(key: ValueKey('usage-warning-pill-hidden'));
    }

    final brightness = Theme.of(context).brightness;
    final label = fraction >= 1 ? 'Allowance reached' : 'Near limit';
    final baseStyle =
        Theme.of(context).textTheme.labelMedium ?? const TextStyle();

    return Container(
      key: const ValueKey('usage-warning-pill'),
      padding: const EdgeInsets.symmetric(
        horizontal: KarmiTokens.s12,
        vertical: KarmiTokens.s8,
      ),
      decoration: BoxDecoration(
        color: KarmiTokens.usageWarningFill(brightness),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ExcludeSemantics(
            child: Icon(
              Icons.warning_amber,
              size: 16,
              color: KarmiTokens.usageWarningIcon(brightness),
            ),
          ),
          const SizedBox(width: KarmiTokens.s4),
          Semantics(
            label: label,
            container: true,
            excludeSemantics: true,
            child: Text(
              label,
              style: baseStyle.copyWith(
                color: KarmiTokens.usageWarningForeground(brightness),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
