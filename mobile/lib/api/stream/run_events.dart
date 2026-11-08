import '../chat/chat_events.dart';
import '../chat/chat_models.dart';

export '../chat/chat_events.dart';
export '../chat/chat_models.dart';

/// Sealed event hierarchy mapping the Karmi SSE streaming contract.
///
/// Aliases the canonical [ChatStreamEvent] from `chat_events.dart`.
typedef RunEvent = ChatStreamEvent;

/// Aliases for individual stream event classes.
typedef RunStarted = RunStartedEvent;
typedef MessageDelta = MessageDeltaEvent;
typedef Heartbeat = HeartbeatEvent;
typedef RunFinished = RunFinishedEvent;
typedef RunError = RunErrorEvent;

/// Compatibility extension providing field aliases for [RunErrorEvent].
extension RunErrorCompat on RunErrorEvent {
  /// Wire field alias for [retryAfterSeconds] matching backend `retry_after_s`.
  int? get retryAfterS => retryAfterSeconds;
}

/// Thrown when an SSE stream fails or is interrupted.
class RunStreamException implements Exception {
  const RunStreamException({
    required this.category,
    this.message,
    this.retryAfterSeconds,
    this.lastSeq,
  });

  /// The categorized failure reason.
  final ErrorCategory category;

  /// Human-readable diagnostic or raw response message.
  final String? message;

  /// Optional backoff suggestion in seconds.
  final int? retryAfterSeconds;

  /// The last sequence number observed before failure, if available.
  final int? lastSeq;

  /// Alias for [retryAfterSeconds].
  int? get retryAfterS => retryAfterSeconds;

  @override
  String toString() =>
      'RunStreamException(category: ${category.wireName}, message: $message, retryAfterSeconds: $retryAfterSeconds, lastSeq: $lastSeq)';
}
