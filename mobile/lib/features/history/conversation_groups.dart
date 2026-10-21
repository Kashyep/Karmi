import '../../api/chat/chat_models.dart';

/// A labeled bucket of conversations for the history list.
class ConversationGroup {
  const ConversationGroup({
    required this.title,
    required this.conversations,
  });

  final String title;
  final List<ConversationView> conversations;

  @override
  String toString() =>
      'ConversationGroup(title: $title, count: ${conversations.length})';
}

/// Groups [conversations] into labeled sections according to §5.7 #1:
/// - Pinned conversations always appear first under the "Pinned" section.
/// - Unpinned conversations are grouped by their local [ConversationView.updatedAt]
///   relative to [now]:
///   - "Today"
///   - "Yesterday"
///   - "Previous 7 days" (2..7 days ago)
///   - "Older" (>7 days ago)
///
/// Empty sections are omitted from the returned list.
List<ConversationGroup> groupConversationsByDate(
  List<ConversationView> conversations, [
  DateTime? now,
]) {
  if (conversations.isEmpty) {
    return const [];
  }

  final current = (now ?? DateTime.now()).toLocal();
  final todayStart = DateTime(current.year, current.month, current.day);
  final yesterdayStart = DateTime(
    todayStart.year,
    todayStart.month,
    todayStart.day - 1,
  );
  final sevenDaysAgoStart = DateTime(
    todayStart.year,
    todayStart.month,
    todayStart.day - 7,
  );

  final pinned = <ConversationView>[];
  final today = <ConversationView>[];
  final yesterday = <ConversationView>[];
  final previous7Days = <ConversationView>[];
  final older = <ConversationView>[];

  for (final conv in conversations) {
    if (conv.pinned) {
      pinned.add(conv);
      continue;
    }

    final localUpdated = conv.updatedAt.toLocal();
    final updatedDate = DateTime(
      localUpdated.year,
      localUpdated.month,
      localUpdated.day,
    );

    if (!updatedDate.isBefore(todayStart)) {
      today.add(conv);
    } else if (updatedDate.isAtSameMomentAs(yesterdayStart)) {
      yesterday.add(conv);
    } else if (!updatedDate.isBefore(sevenDaysAgoStart)) {
      previous7Days.add(conv);
    } else {
      older.add(conv);
    }
  }

  final groups = <ConversationGroup>[];
  if (pinned.isNotEmpty) {
    groups.add(ConversationGroup(title: 'Pinned', conversations: pinned));
  }
  if (today.isNotEmpty) {
    groups.add(ConversationGroup(title: 'Today', conversations: today));
  }
  if (yesterday.isNotEmpty) {
    groups.add(ConversationGroup(title: 'Yesterday', conversations: yesterday));
  }
  if (previous7Days.isNotEmpty) {
    groups.add(
      ConversationGroup(
        title: 'Previous 7 days',
        conversations: previous7Days,
      ),
    );
  }
  if (older.isNotEmpty) {
    groups.add(ConversationGroup(title: 'Older', conversations: older));
  }

  return groups;
}
