import '../../api/bug_reports/bug_report_errors.dart';

/// Formats seconds into human-readable plain language (e.g. '1 hour', '2 hours', '45 minutes', '1 minute').
String formatRetryAfterDuration(int seconds) {
  if (seconds <= 60) {
    return '1 minute';
  }
  if (seconds < 3600) {
    final minutes = (seconds / 60).ceil();
    return '$minutes ${minutes == 1 ? "minute" : "minutes"}';
  }
  final hours = (seconds / 3600).ceil();
  return '$hours ${hours == 1 ? "hour" : "hours"}';
}

/// Builds the complete user message for 429 rate limit.
String formatRetryAfterMessage(int seconds) {
  return 'You have sent 3 reports today. Try again in ${formatRetryAfterDuration(seconds)}.';
}

/// Alias for [mapBugReportErrorToPlainWords].
String mapBugReportErrorToMessage(Object error) =>
    mapBugReportErrorToPlainWords(error);

/// Maps any bug report error into user-facing plain words without raw codes or JSON.
String mapBugReportErrorToPlainWords(Object error) {
  if (error is BugReportRateLimitException) {
    final duration = formatRetryAfterDuration(error.retryAfterSeconds);
    return 'You have sent 3 reports today. Try again in $duration.';
  }

  if (error is BugReportPayloadTooLargeException) {
    return 'That screenshot is too big. Turn off the screenshot or try again.';
  }

  if (error is BugReportUnsupportedMediaTypeException) {
    return 'That screenshot type is not supported. Turn off the screenshot.';
  }

  if (error is BugReportValidationException) {
    return 'Some details were not accepted. Please try again from the app update.';
  }

  if (error is BugReportConflictException ||
      error is IdempotencyConflictException) {
    return 'This bug report could not be submitted because of a conflict. Please start a new report.';
  }

  if (error is NetworkException) {
    return "You appear to be offline. Your report has been saved and will send when you're back online.";
  }

  if (error is ApiTimeoutException) {
    return 'Sending took too long. We saved your report and will try again automatically.';
  }

  if (error is UnauthorizedException) {
    return 'Your session has expired. Please sign in again to submit.';
  }

  if (error is ServerException) {
    final code = error.statusCode;
    if (code == 413) {
      return 'That screenshot is too big. Turn off the screenshot or try again.';
    }
    if (code == 415) {
      return 'That screenshot type is not supported. Turn off the screenshot.';
    }
    if (code == 422) {
      return 'Some details were not accepted. Please try again from the app update.';
    }
    if (code == 409) {
      return 'This bug report could not be submitted because of a conflict. Please start a new report.';
    }
    if (code == 429) {
      return 'You have sent 3 reports today. Try again later.';
    }
    return "Couldn't reach the server right now. We saved your report and will try again automatically.";
  }

  return 'Something went wrong while sending your report. Please try again.';
}
