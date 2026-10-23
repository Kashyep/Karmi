import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_tokens.dart';

/// Selectable card with radio/check indicator, headline, description, and optional icon.
class ChoiceTile extends StatelessWidget {
  const ChoiceTile({
    super.key,
    required this.title,
    this.description,
    this.icon,
    required this.isSelected,
    required this.onTap,
  });

  final String title;
  final String? description;
  final Widget? icon;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return Semantics(
      selected: isSelected,
      button: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: KarmiTokens.fast,
            constraints: const BoxConstraints(minHeight: 56),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isSelected ? colors.card : colors.background,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected ? colors.primary : colors.borderSubtle,
                width: isSelected ? 1.5 : 1.0,
              ),
            ),
            child: Row(
              children: [
                if (icon != null) ...[
                  icon!,
                  const SizedBox(width: 14),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        style: textTheme.titleMedium?.copyWith(
                          color: colors.foreground,
                          fontWeight:
                              isSelected ? FontWeight.w600 : FontWeight.w500,
                        ),
                      ),
                      if (description != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          description!,
                          style: textTheme.bodySmall?.copyWith(
                            color: colors.mutedForeground,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: isSelected ? colors.primary : colors.border,
                      width: 2,
                    ),
                    color: isSelected ? colors.primary : Colors.transparent,
                  ),
                  child: isSelected
                      ? Icon(
                          Icons.check,
                          size: 14,
                          color: colors.primaryForeground,
                        )
                      : null,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
