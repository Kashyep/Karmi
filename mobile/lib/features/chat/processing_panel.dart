import 'package:flutter/material.dart';

// Canonical definition belongs in features/chat/state/chat_controller.dart (Squad A); move at merge.
enum ChatRunPhase { idle, sending, streaming, stalled, finished, error }

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

    final disableAnimations = MediaQuery.disableAnimationsOf(context);
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

    return Semantics(
      liveRegion: true,
      label: label,
      child: AnimatedSwitcher(
        duration: duration,
        child: Padding(
          key: ValueKey(phase),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox.square(
                dimension: 14,
                child: disableAnimations
                    ? Icon(
                        Icons.more_horiz,
                        size: 14,
                        color: colorScheme.onSurfaceVariant,
                      )
                    : CircularProgressIndicator(
                        strokeWidth: 2,
                        color: colorScheme.primary,
                      ),
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                  fontWeight: FontWeight.w500,
                ),
              ),
              if (subtleLabel != null) ...[
                const SizedBox(width: 6),
                Text(
                  subtleLabel,
                  style: textTheme.labelSmall?.copyWith(
                    color: colorScheme.outline,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
