import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../theme/karmi_motion.dart';
import 'state/chat_controller.dart';
/// Displays staged summary during assistant generation without exposing model reasoning.
class ProcessingPanel extends StatelessWidget {
  const ProcessingPanel({super.key, required this.phase});

  final ChatRunPhase phase;

  @override
  Widget build(BuildContext context) {
    if (phase == ChatRunPhase.idle ||
        phase == ChatRunPhase.finished ||
        phase == ChatRunPhase.error) {
      return const SizedBox.shrink();
    }

    final disableAnimations = KarmiAccessibility.reduceMotionOf(context);
    final duration = disableAnimations
        ? Duration.zero
        : const Duration(milliseconds: 200);

    final String label;
    final String? subtleLabel;

    switch (phase) {
      case ChatRunPhase.sending:
        label = 'Preparing';
        subtleLabel = null;
        break;
      case ChatRunPhase.streaming:
        label = 'Writing';
        subtleLabel = null;
        break;
      case ChatRunPhase.stalled:
        label = 'Still working…';
        subtleLabel = 'Connection slow';
        break;
      case ChatRunPhase.idle:
      case ChatRunPhase.finished:
      case ChatRunPhase.error:
        return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final textTheme = theme.textTheme;
    final karmiColors = theme.extension<KarmiColors>();

    final surfaceColor =
        karmiColors?.sidebarSurface ?? colorScheme.surfaceContainerLow;
    final borderColor =
        karmiColors?.borderSubtle ?? colorScheme.outlineVariant;
    final primaryTextColor =
        karmiColors?.primaryText ?? colorScheme.primary;
    final textColor =
        karmiColors?.foreground ?? colorScheme.onSurfaceVariant;
    final subtleColor =
        karmiColors?.mutedForeground ?? colorScheme.outline;

    return Semantics(
      liveRegion: true,
      label: label,
      child: AnimatedSwitcher(
        duration: duration,
        child: Padding(
          key: ValueKey(phase),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Container(
              decoration: BoxDecoration(
                color: surfaceColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: borderColor, width: 1),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox.square(
                    dimension: 14,
                    child: disableAnimations
                        ? Icon(
                            Icons.more_horiz,
                            size: 14,
                            color: subtleColor,
                          )
                        : CircularProgressIndicator(
                            strokeWidth: 2,
                            color: primaryTextColor,
                          ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    label,
                    style: textTheme.bodySmall?.copyWith(
                      color: textColor,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (subtleLabel != null) ...[
                    const SizedBox(width: 8),
                    Text(
                      subtleLabel,
                      style: textTheme.labelSmall?.copyWith(
                        color: subtleColor,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
