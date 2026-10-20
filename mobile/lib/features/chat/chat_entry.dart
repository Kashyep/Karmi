import '../../api/models.dart';

/// Delivery state of a message the user typed.
enum SendState {
  sending,
  sent,
  failed,
  offline,
  inFlight,
  limitReached,
  capacityFull,
}

/// One row in the local, in-memory transcript. There is no history endpoint,
/// so the transcript is not persisted.
sealed class ChatEntry {
  const ChatEntry(this.id);

  final String id;
}

/// A message the user typed. Its [idempotencyKey] is reused on every retry so
/// the server replays the original run instead of charging again.
final class UserEntry extends ChatEntry {
  UserEntry({
    required String id,
    required this.text,
    required this.idempotencyKey,
    this.state = SendState.sending,
  }) : super(id);

  final String text;
  final String idempotencyKey;
  SendState state;

  /// Allowance or beta-capacity reset time from a 429 response, when known.
  DateTime? resetAt;
}

/// A server reply (`MessageView`).
final class ReplyEntry extends ChatEntry {
  const ReplyEntry({
    required String id,
    required this.message,
    this.feedbackRating,
    this.feedbackReason,
    this.isFeedbackInFlight = false,
    this.isRegenerating = false,
  }) : super(id);

  final MessageView message;
  final FeedbackRating? feedbackRating;
  final String? feedbackReason;
  final bool isFeedbackInFlight;
  final bool isRegenerating;

  ReplyEntry copyWith({
    String? id,
    MessageView? message,
    FeedbackRating? feedbackRating,
    String? feedbackReason,
    bool clearReason = false,
    bool? isFeedbackInFlight,
    bool? isRegenerating,
  }) => ReplyEntry(
    id: id ?? this.id,
    message: message ?? this.message,
    feedbackRating: feedbackRating ?? this.feedbackRating,
    feedbackReason: clearReason
        ? null
        : (feedbackReason ?? this.feedbackReason),
    isFeedbackInFlight: isFeedbackInFlight ?? this.isFeedbackInFlight,
    isRegenerating: isRegenerating ?? this.isRegenerating,
  );
}
