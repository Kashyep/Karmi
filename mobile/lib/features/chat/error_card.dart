import 'package:flutter/material.dart';

import '../../api/chat/chat_models.dart';
import '../../theme/karmi_colors.dart';
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

  // Recoverable warning categories (resumeUnavailable, quotaExhausted, unauthorized) use warningSurface; fatal errors use errorSurface.
  bool get _isWarning => switch (category) {
    ErrorCategory.resumeUnavailable ||
    ErrorCategory.quotaExhausted ||
    ErrorCategory.unauthorized => true,
    ErrorCategory.capacityFull ||
    ErrorCategory.providerUnavailable ||
    ErrorCategory.validationFailed ||
    ErrorCategory.network ||
    ErrorCategory.internal => false,
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final karmiColors = theme.extension<KarmiColors>();
    final message = messageFor(category);
    final action = _actionFor(category);

    final cardColor = karmiColors != null
        ? (_isWarning ? karmiColors.warningSurface : karmiColors.errorSurface)
        : colorScheme.errorContainer;

    final borderColor = karmiColors != null
        ? (_isWarning
            ? karmiColors.warning.withValues(alpha: 0.3)
            : karmiColors.destructive.withValues(alpha: 0.3))
        : colorScheme.outlineVariant;

    final contentColor =
        karmiColors?.foreground ?? colorScheme.onErrorContainer;

    final iconColor = karmiColors != null
        ? (_isWarning ? karmiColors.warning : karmiColors.destructive)
        : colorScheme.onErrorContainer;

    final buttonBgColor = karmiColors != null
        ? (_isWarning
            ? karmiColors.warning.withValues(alpha: 0.16)
            : karmiColors.destructive.withValues(alpha: 0.16))
        : colorScheme.onErrorContainer.withValues(alpha: 0.12);

    final buttonBorderColor = karmiColors != null
        ? (_isWarning
            ? karmiColors.warning.withValues(alpha: 0.35)
            : karmiColors.destructive.withValues(alpha: 0.35))
        : colorScheme.onErrorContainer.withValues(alpha: 0.25);

    return Semantics(
      container: true,
      liveRegion: true,
      label: message,
      child: Card(
        elevation: 0,
        margin: EdgeInsets.zero,
        color: cardColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: borderColor, width: 1),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            children: [
              Icon(
                iconFor(category),
                size: 20,
                color: iconColor,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  message,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: contentColor,
                  ),
                ),
              ),
              if (action != null) ...[
                const SizedBox(width: 8),
                Tooltip(
                  message: action.$2,
                  child: Semantics(
                    button: true,
                    label: action.$2,
                    child: TextButton(
                      onPressed: action.$1,
                      style: TextButton.styleFrom(
                        foregroundColor: contentColor,
                        backgroundColor: buttonBgColor,
                        side: BorderSide(color: buttonBorderColor, width: 1),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 8,
                        ),
                        minimumSize: const Size(48, 48),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: Text(
                        action.$2,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
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
