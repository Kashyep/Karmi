/// Typed failures from [KarmiApi]. Screens map these to copy; raw text is never shown.
sealed class KarmiApiException implements Exception {
  const KarmiApiException();
}

/// HTTP 401: missing, expired or revoked session (`security.require_principal`).
final class UnauthorizedException extends KarmiApiException {
  const UnauthorizedException();
}

/// HTTP 409 from `POST /v1/messages` while the same idempotency key is still
/// reserved (`services.ReservationInFlight`). Retrying with the same key observes the result.
final class InFlightException extends KarmiApiException {
  const InFlightException();
}

/// HTTP 409 `idempotency key was reused with a different payload`.
final class IdempotencyConflictException extends KarmiApiException {
  const IdempotencyConflictException();
}

/// HTTP 429 with `detail.code == "ALLOWANCE_EXHAUSTED"` (`services.BudgetDenied`).
final class LimitReachedException extends KarmiApiException {
  const LimitReachedException({this.resetAt});

  /// When the allowance resets, if the server sent a parseable `detail.reset_at`.
  final DateTime? resetAt;
}

/// The request never produced an HTTP response (socket error, client error or timeout).
final class NetworkException extends KarmiApiException {
  const NetworkException();
}

/// Any other non-success status, or a response body that could not be parsed.
final class ServerException extends KarmiApiException {
  const ServerException(this.statusCode);

  final int statusCode;
}
