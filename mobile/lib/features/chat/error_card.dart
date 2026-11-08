import 'package:flutter/material.dart';

import '../../api/bug_reports/bug_report_models.dart';
import '../../api/chat/chat_models.dart';
import '../../auth/session.dart';
import '../../theme/karmi_colors.dart';
import '../bug_report/bug_report_screen.dart';

/// User-facing card for errors during assistant runs.
class ErrorCard extends StatelessWidget {
  const ErrorCard({
    super.key,
    required this.category,
    this.errorCode,
    this.onRetry,
    this.onContinue,
    this.onUpgrade,
    this.session,
    this.userId,
  });

  final ErrorCategory category;
  final VoidCallback? onRetry;
  final VoidCallback? onContinue;
  final VoidCallback? onUpgrade;
  final String? errorCode;
  final KarmiSession? session;
  final String? userId;

  void _openBugReport(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => BugReportScreen(
          api: session?.api,
          session: session,
          userId: userId ?? session?.userId,
          initialCategory: BugReportCategory.chat,
          initialScreen: 'chat',
          initialErrorCode: errorCode ?? category.name,
        ),
      ),
    );
  }

  /// Pure helper returning the user-facing message for the error category.
  static String messageFor(ErrorCategory category) => switch (category) {
    ErrorCategory.quotaExhausted => "You've reached your plan limit for now.",
    ErrorCategory.capacityFull => 'Karmi is busy right now.',
    ErrorCategory.providerUnavailable => "Karmi couldn't finish this reply.",
    ErrorCategory.validationFailed => 'This response could not be displayed.',
    ErrorCategory.unauthorized => 'Your session has expired.',
    ErrorCategory.resumeUnavailable => 'The connection was interrupted.',
    ErrorCategory.network => 'You appear to be offline.',
    ErrorCategory.timeout => 'Karmi took too long to respond.',
    ErrorCategory.internal => 'Something went wrong on our end.',
  };

  /// Pure helper determining if the category is retryable by the user.
  static bool isRetryable(ErrorCategory category) => switch (category) {
    ErrorCategory.capacityFull ||
    ErrorCategory.providerUnavailable ||
    ErrorCategory.validationFailed ||
    ErrorCategory.network ||
    ErrorCategory.timeout ||
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
    ErrorCategory.timeout => Icons.schedule_rounded,
    ErrorCategory.internal => Icons.error_outline,
  };

  ({VoidCallback callback, String label})? _actionFor(
    ErrorCategory category,
  ) => switch (category) {
    ErrorCategory.quotaExhausted =>
      onUpgrade != null ? (callback: onUpgrade!, label: 'View plans') : null,
    ErrorCategory.capacityFull =>
      onRetry != null ? (callback: onRetry!, label: 'Try again') : null,
    ErrorCategory.providerUnavailable =>
      onRetry != null ? (callback: onRetry!, label: 'Retry') : null,
    ErrorCategory.validationFailed =>
      onRetry != null ? (callback: onRetry!, label: 'Regenerate') : null,
    ErrorCategory.unauthorized =>
      onRetry != null ? (callback: onRetry!, label: 'Sign in') : null,
    ErrorCategory.resumeUnavailable =>
      onContinue != null ? (callback: onContinue!, label: 'Continue') : null,
    ErrorCategory.network =>
      onRetry != null ? (callback: onRetry!, label: 'Retry') : null,
    ErrorCategory.timeout =>
      onRetry != null ? (callback: onRetry!, label: 'Retry') : null,
    ErrorCategory.internal =>
      onRetry != null ? (callback: onRetry!, label: 'Retry') : null,
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
    ErrorCategory.timeout ||
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
              Icon(iconFor(category), size: 20, color: iconColor),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      message,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: contentColor,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Semantics(
                      button: true,
                      label: 'Report this problem',
                      child: InkWell(
                        key: const ValueKey('error_card_report_link'),
                        onTap: () => _openBugReport(context),
                        borderRadius: BorderRadius.circular(4),
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            minWidth: 48,
                            minHeight: 48,
                          ),
                          child: Align(
                            alignment: Alignment.centerLeft,
                            widthFactor: 1.0,
                            heightFactor: 1.0,
                            child: Text(
                              'Report this',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: contentColor,
                                decoration: TextDecoration.underline,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (action != null) ...[
                const SizedBox(width: 8),
                Tooltip(
                  message: action.label,
                  child: Semantics(
                    button: true,
                    label: action.label,
                    child: TextButton(
                      onPressed: action.callback,
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
                        action.label,
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
