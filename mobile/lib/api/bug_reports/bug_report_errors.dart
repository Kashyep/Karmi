export '../errors.dart'
    show
        KarmiApiException,
        NetworkException,
        ApiTimeoutException,
        ServerException,
        UnauthorizedException,
        IdempotencyConflictException;

/// Base class for bug report specific API exceptions.
sealed class BugReportApiException implements Exception {
  const BugReportApiException();
}

/// HTTP 429: Rate limit exceeded (maximum 3 new reports per 24 hours).
final class BugReportRateLimitException extends BugReportApiException {
  const BugReportRateLimitException({required this.retryAfterSeconds});

  final int retryAfterSeconds;

  @override
  String toString() =>
      'BugReportRateLimitException(retryAfterSeconds: $retryAfterSeconds)';
}

/// HTTP 413: Screenshot or payload too large (> 5 MB).
final class BugReportPayloadTooLargeException extends BugReportApiException {
  const BugReportPayloadTooLargeException([this.message]);

  final String? message;

  @override
  String toString() =>
      'BugReportPayloadTooLargeException(${message ?? "payload exceeds limit"})';
}

/// HTTP 415: Unsupported media type (not image/png or image/jpeg, or magic mismatch).
final class BugReportUnsupportedMediaTypeException
    extends BugReportApiException {
  const BugReportUnsupportedMediaTypeException([this.message]);

  final String? message;

  @override
  String toString() =>
      'BugReportUnsupportedMediaTypeException(${message ?? "unsupported media type"})';
}

/// HTTP 422: Validation error (invalid fields, unknown diagnostics keys, invalid description).
final class BugReportValidationException extends BugReportApiException {
  const BugReportValidationException([this.message]);

  final String? message;

  @override
  String toString() =>
      'BugReportValidationException(${message ?? "validation failed"})';
}

/// HTTP 409: Idempotency conflict (client_report_id reused with different payload).
final class BugReportConflictException extends BugReportApiException {
  const BugReportConflictException([this.message]);

  final String? message;

  @override
  String toString() =>
      'BugReportConflictException(${message ?? "client_report_id reused with different payload"})';
}

/// HTTP 404: Bug report not found.
final class BugReportNotFoundException extends BugReportApiException {
  const BugReportNotFoundException();

  @override
  String toString() => 'BugReportNotFoundException()';
}
