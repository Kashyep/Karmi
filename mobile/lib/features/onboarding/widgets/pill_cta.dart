import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_motion.dart';

/// Full-width or inline rounded high-contrast primary call-to-action button.
/// Loading spinner replacement when busy.
class PillCta extends StatelessWidget {
  const PillCta({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.enabled = true,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final bool enabled;
  final Widget? icon;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final isClickable = enabled && !isLoading && onPressed != null;

    return AnimatedContainer(
      duration: KarmiMotion.fast,
      height: 52,
      constraints: const BoxConstraints(minWidth: 120, minHeight: 48),
      child: Semantics(
        button: true,
        enabled: isClickable,
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: colors.primary,
            foregroundColor: colors.primaryForeground,
            disabledBackgroundColor: colors.muted,
            disabledForegroundColor: colors.mutedForeground,
            shape: const StadiumBorder(),
            elevation: 0,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            minimumSize: const Size(48, 48),
          ),
          onPressed: isClickable ? onPressed : null,
          child: isLoading
              ? SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      colors.primaryForeground,
                    ),
                  ),
                )
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    if (icon != null) ...[
                      icon!,
                      const SizedBox(width: 8),
                    ],
                    Text(
                      label,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: isClickable
                                ? colors.primaryForeground
                                : colors.mutedForeground,
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
