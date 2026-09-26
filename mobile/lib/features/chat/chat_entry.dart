import '../../api/models.dart';

/// Delivery state of a message the user typed.
enum SendState { sending, sent, failed, offline, inFlight, limitReached }

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

  /// Allowance reset time from a 429 response, when known.
  DateTime? resetAt;
}

/// A server reply (`MessageView`).
final class ReplyEntry extends ChatEntry {
  const ReplyEntry({required String id, required this.message}) : super(id);

  final MessageView message;
}
