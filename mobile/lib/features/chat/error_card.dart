import 'package:flutter/material.dart';

import '../../api/chat/chat_models.dart';

/// User-facing card for errors during assistant runs.
class ErrorCard extends StatelessWidget {
  const ErrorCard({
    super.key,
    required this.category,
    this.onRetry,
    this.onContinue,
    this.onUpgrade,
  });

  final ErrorCategory category;
  final VoidCallback? onRetry;
  final VoidCallback? onContinue;
  final VoidCallback? onUpgrade;

  /// Pure helper returning the user-facing message for the error category.
  static String messageFor(ErrorCategory category) => switch (category) {
    ErrorCategory.quotaExhausted => "You've reached your plan limit for now.",
    ErrorCategory.capacityFull => 'Karmi is busy right now.',
    ErrorCategory.providerUnavailable => 'The model service had a problem.',
    ErrorCategory.validationFailed =>
      'This reply was blocked or came back empty.',
    ErrorCategory.unauthorized => 'Your session expired. Sign in again.',
    ErrorCategory.resumeUnavailable => 'Connection lost. Partial reply kept.',
    ErrorCategory.network => 'You appear to be offline.',
    ErrorCategory.internal => 'Something went wrong.',
  };

  /// Pure helper determining if the category is retryable by the user.
  static bool isRetryable(ErrorCategory category) => switch (category) {
    ErrorCategory.capacityFull ||
    ErrorCategory.providerUnavailable ||
    ErrorCategory.validationFailed ||
    ErrorCategory.network ||
    ErrorCategory.internal => true,
    ErrorCategory.quotaExhausted ||
    ErrorCategory.unauthorized ||
    ErrorCategory.resumeUnavailable => false,
  };

  static IconData iconFor(ErrorCategory category) => switch (category) {
    ErrorCategory.quotaExhausted => Icons.lock_clock_outlined,
    ErrorCategory.capacityFull => Icons.hourglass_top_outlined,
    ErrorCategory.providerUnavailable => Icons.cloud_off_outlined,
    ErrorCategory.validationFailed => Icons.shield_outlined,
    ErrorCategory.unauthorized => Icons.lock_outline,
    ErrorCategory.resumeUnavailable => Icons.sync_problem_outlined,
    ErrorCategory.network => Icons.wifi_off_rounded,
    ErrorCategory.internal => Icons.error_outline,
  };

  (VoidCallback, String)? _actionFor(ErrorCategory category) =>
      switch (category) {
        ErrorCategory.quotaExhausted =>
          onUpgrade != null ? (onUpgrade!, 'View plans') : null,
        ErrorCategory.capacityFull =>
          onRetry != null ? (onRetry!, 'Try again') : null,
        ErrorCategory.providerUnavailable =>
          onRetry != null ? (onRetry!, 'Retry') : null,
        ErrorCategory.validationFailed =>
          onRetry != null ? (onRetry!, 'Regenerate') : null,
        ErrorCategory.unauthorized =>
          onRetry != null ? (onRetry!, 'Sign in') : null,
        ErrorCategory.resumeUnavailable =>
          onContinue != null ? (onContinue!, 'Continue') : null,
        ErrorCategory.network => onRetry != null ? (onRetry!, 'Retry') : null,
        ErrorCategory.internal => onRetry != null ? (onRetry!, 'Retry') : null,
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final message = messageFor(category);
    final action = _actionFor(category);
    final errorContainer = colorScheme.errorContainer;
    final onErrorContainer = colorScheme.onErrorContainer;
    final lBg = errorContainer.computeLuminance();
    final lFg = onErrorContainer.computeLuminance();
    final ratio = (lBg > lFg ? lBg + 0.05 : lFg + 0.05) /
        (lBg > lFg ? lFg + 0.05 : lBg + 0.05);
    final bg = ratio < 4.5
        ? (lBg > 0.5 ? const Color(0xFFFDE8E8) : const Color(0xFF4A0E14))
        : errorContainer;
    final foreground = ratio < 4.5
        ? (lBg > 0.5 ? const Color(0xFF7A141E) : const Color(0xFFFFDAD6))
        : onErrorContainer;
    return Semantics(
      container: true,
      liveRegion: true,
      label: message,
      child: Card(
        elevation: 0,
        margin: EdgeInsets.zero,
        color: bg,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            children: [
              Icon(
                iconFor(category),
                size: 20,
                color: foreground,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  message,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: foreground,
                  ),
                ),
              ),
              if (action != null) ...[
                const SizedBox(width: 8),
                Tooltip(
                  message: action.$2,
                  textStyle: const TextStyle(color: Colors.white, fontSize: 12),
                  decoration: BoxDecoration(
                    color: const Color(0xFF202020),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: TextButton(
                    onPressed: action.$1,
                    style: TextButton.styleFrom(
                      foregroundColor: foreground,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      minimumSize: const Size(48, 48),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                        side: BorderSide(
                          color: foreground.withValues(
                            alpha: 0.3,
                          ),
                        ),
                      ),
                    ),
                    child: Text(
                      action.$2,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
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
