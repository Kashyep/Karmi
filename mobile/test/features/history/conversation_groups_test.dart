import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/features/history/conversation_groups.dart';
import 'package:karmi_app/features/history/conversation_list.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';

class _FakeApi implements ConversationsApi {
  List<ConversationView> conversations = [];

  @override
  String baseUrl = 'http://test';
  @override
  Duration timeout = const Duration(seconds: 1);
  @override
  Future<String?> Function()? tokenProvider;
  @override
  void close() {}
  @override
  Future<ConversationPage> list({
    bool archived = false,
    String? cursor,
    int limit = 20,
  }) async =>
      ConversationPage(items: conversations);
  @override
  Future<List<ConversationSearchResult>> search(String q, {int limit = 20}) async =>
      [];
  @override
  Future<ConversationView> get(String id) async =>
      conversations.firstWhere((c) => c.id == id);
  @override
  Future<MessagePage> messages(String id, {String? before, int limit = 50}) async =>
      const MessagePage(items: []);
  @override
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async =>
      conversations.firstWhere((c) => c.id == id);
  @override
  Future<void> delete(String id) async {}
  @override
  Future<ConversationView> restore(String id) async =>
      conversations.firstWhere((c) => c.id == id);
}
void main() {
  group('groupConversationsByDate', () {
    final now = DateTime.utc(2026, 10, 22, 14, 30, 0);

    test('returns empty list when input is empty', () {
      final groups = groupConversationsByDate([], now);
      expect(groups, isEmpty);
    });

    test('pinned conversations always appear under "Pinned" section first', () {
      final conversations = [
        ConversationView(
          id: 'c1',
          title: 'Unpinned today',
          pinned: false,
          updatedAt: now.subtract(const Duration(hours: 1)),
        ),
        ConversationView(
          id: 'c2',
          title: 'Pinned older',
          pinned: true,
          updatedAt: now.subtract(const Duration(days: 30)),
        ),
        ConversationView(
          id: 'c3',
          title: 'Pinned today',
          pinned: true,
          updatedAt: now.subtract(const Duration(minutes: 10)),
        ),
      ];

      final groups = groupConversationsByDate(conversations, now);

      expect(groups.length, 2);
      expect(groups[0].title, 'Pinned');
      expect(groups[0].conversations.map((c) => c.id).toList(), ['c2', 'c3']);
      expect(groups[1].title, 'Today');
      expect(groups[1].conversations.map((c) => c.id).toList(), ['c1']);
    });

    test('groups conversations into Today, Yesterday, Previous 7 days, and Older', () {
      final localNow = now.toLocal();
      final todayStart = DateTime(localNow.year, localNow.month, localNow.day);

      final conversations = [
        // Today
        ConversationView(
          id: 'today_1',
          title: 'Today chat',
          pinned: false,
          updatedAt: todayStart.add(const Duration(hours: 3)),
        ),
        // Yesterday
        ConversationView(
          id: 'yesterday_1',
          title: 'Yesterday chat',
          pinned: false,
          updatedAt: todayStart.subtract(const Duration(hours: 5)),
        ),
        // Previous 7 days (3 days ago)
        ConversationView(
          id: 'prev7_1',
          title: '3 days ago',
          pinned: false,
          updatedAt: todayStart.subtract(const Duration(days: 3)),
        ),
        // Previous 7 days (7 days ago)
        ConversationView(
          id: 'prev7_2',
          title: '7 days ago',
          pinned: false,
          updatedAt: todayStart.subtract(const Duration(days: 7)),
        ),
        // Older (8 days ago)
        ConversationView(
          id: 'older_1',
          title: '8 days ago',
          pinned: false,
          updatedAt: todayStart.subtract(const Duration(days: 8)),
        ),
        // Older (40 days ago)
        ConversationView(
          id: 'older_2',
          title: '40 days ago',
          pinned: false,
          updatedAt: todayStart.subtract(const Duration(days: 40)),
        ),
      ];

      final groups = groupConversationsByDate(conversations, now);

      expect(groups.map((g) => g.title).toList(), [
        'Today',
        'Yesterday',
        'Previous 7 days',
        'Older',
      ]);

      expect(groups[0].conversations.map((c) => c.id).toList(), ['today_1']);
      expect(groups[1].conversations.map((c) => c.id).toList(), ['yesterday_1']);
      expect(groups[2].conversations.map((c) => c.id).toList(), ['prev7_1', 'prev7_2']);
      expect(groups[3].conversations.map((c) => c.id).toList(), ['older_1', 'older_2']);
    });

    test('omits empty date buckets', () {
      final localNow = now.toLocal();
      final todayStart = DateTime(localNow.year, localNow.month, localNow.day);

      final conversations = [
        ConversationView(
          id: 'c_today',
          title: 'Today only',
          pinned: false,
          updatedAt: todayStart.add(const Duration(hours: 1)),
        ),
        ConversationView(
          id: 'c_older',
          title: 'Older only',
          pinned: false,
          updatedAt: todayStart.subtract(const Duration(days: 15)),
        ),
      ];

      final groups = groupConversationsByDate(conversations, now);

      expect(groups.map((g) => g.title).toList(), ['Today', 'Older']);
    });
  });

  group('ConversationList grouped sections & active highlight', () {
    testWidgets('renders section headers and active row highlight', (tester) async {
      final now = DateTime.now();
      final api = _FakeApi();
      api.conversations = [
        ConversationView(
          id: 'pinned_1',
          title: 'Pinned item',
          pinned: true,
          updatedAt: now.subtract(const Duration(minutes: 5)),
        ),
        ConversationView(
          id: 'today_1',
          title: 'Today item',
          pinned: false,
          updatedAt: now.subtract(const Duration(minutes: 10)),
        ),
        ConversationView(
          id: 'older_1',
          title: 'Older item',
          pinned: false,
          updatedAt: now.subtract(const Duration(days: 20)),
        ),
      ];

      final controller = ConversationListController(
        api: api,
        searchDebounce: const Duration(milliseconds: 10),
      );

      await controller.refresh();

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ConversationList(
              controller: controller,
              activeConversationId: 'today_1',
              onOpen: (_) {},
              onNewChat: () {},
            ),
          ),
        ),
      );
      await tester.pump();

      // Section headers are displayed
      expect(find.text('Pinned'), findsOneWidget);
      expect(find.text('Today'), findsOneWidget);
      expect(find.text('Older'), findsOneWidget);

      // Conversation titles are rendered
      expect(find.text('Pinned item'), findsOneWidget);
      expect(find.text('Today item'), findsOneWidget);
      expect(find.text('Older item'), findsOneWidget);

      // Active row has FontWeight.w500
      final todayTextWidget = tester.widget<Text>(find.text('Today item'));
      expect(todayTextWidget.style?.fontWeight, FontWeight.w500);

      // Inactive row does not have w500
      final olderTextWidget = tester.widget<Text>(find.text('Older item'));
      expect(olderTextWidget.style?.fontWeight, isNot(FontWeight.w500));

      controller.dispose();
    });
  });
}
