import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/features/history/conversation_list.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/features/history/search_field.dart';

class FakeConversationsApi implements ConversationsApi {
  List<ConversationView> conversations = [];
  List<ConversationSearchResult> searchResults = [];
  final List<String> deletedIds = [];
  final List<String> restoredIds = [];

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
  }) async {
    final filtered = conversations
        .where((c) => (c.archivedAt != null) == archived)
        .toList();
    return ConversationPage(items: filtered, nextCursor: null);
  }

  @override
  Future<List<ConversationSearchResult>> search(
    String q, {
    int limit = 20,
  }) async {
    return searchResults;
  }

  @override
  Future<ConversationView> get(String id) async {
    return conversations.firstWhere((c) => c.id == id);
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    return const MessagePage(items: []);
  }

  @override
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async {
    final idx = conversations.indexWhere((c) => c.id == id);
    if (idx == -1) throw Exception('Not found');
    final old = conversations[idx];
    final updated = old.copyWith(
      title: title ?? old.title,
      pinned: pinned ?? old.pinned,
      archivedAt: archived != null
          ? (archived ? DateTime.now() : null)
          : old.archivedAt,
    );
    conversations[idx] = updated;
    return updated;
  }

  @override
  Future<void> delete(String id) async {
    deletedIds.add(id);
    conversations.removeWhere((c) => c.id == id);
  }

  @override
  Future<ConversationView> restore(String id) async {
    restoredIds.add(id);
    final restored = ConversationView(
      id: id,
      title: 'Restored chat',
      updatedAt: DateTime.now(),
    );
    conversations.add(restored);
    return restored;
  }
}

void main() {
  group('ConversationList', () {
    late FakeConversationsApi api;
    late ConversationListController controller;
    late DateTime testNow;

    setUp(() {
      testNow = DateTime.utc(2026, 10, 21, 12, 0, 0);
      api = FakeConversationsApi();
      controller = ConversationListController(
        api: api,
        searchDebounce: const Duration(milliseconds: 10),
        undoWindow: const Duration(seconds: 5),
      );
    });

    tearDown(() {
      controller.dispose();
    });

    Widget buildTestWidget({
      required ValueChanged<String> onOpen,
      required VoidCallback onNewChat,
    }) {
      return MaterialApp(
        home: Scaffold(
          body: ConversationList(
            controller: controller,
            onOpen: onOpen,
            onNewChat: onNewChat,
          ),
        ),
      );
    }

    testWidgets('renders titles, fallback title, and pinned indicator', (
      tester,
    ) async {
      api.conversations = [
        ConversationView(
          id: 'conv_1',
          title: 'Project Roadmap',
          pinned: true,
          updatedAt: testNow.subtract(const Duration(minutes: 5)),
        ),
        ConversationView(
          id: 'conv_2',
          title: null,
          pinned: false,
          updatedAt: testNow.subtract(const Duration(hours: 2)),
        ),
      ];

      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () {}),
      );
      await tester.pump();

      expect(find.text('Project Roadmap'), findsOneWidget);
      expect(find.text('Untitled chat'), findsOneWidget);
      expect(find.byIcon(Icons.push_pin), findsOneWidget);
    });

    testWidgets('tapping conversation row calls onOpen with id', (
      tester,
    ) async {
      api.conversations = [
        ConversationView(
          id: 'conv_42',
          title: 'Deep dive discussion',
          updatedAt: testNow,
        ),
      ];

      String? openedId;
      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (id) => openedId = id, onNewChat: () {}),
      );
      await tester.pump();

      await tester.tap(find.text('Deep dive discussion'));
      await tester.pump();

      expect(openedId, 'conv_42');
    });

    testWidgets('tapping new chat button calls onNewChat', (tester) async {
      bool newChatCalled = false;
      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () => newChatCalled = true),
      );
      await tester.pump();

      await tester.tap(find.byKey(const ValueKey('new-chat-button')));
      await tester.pump();

      expect(newChatCalled, isTrue);
    });

    testWidgets('search field typing updates query and shows search results', (
      tester,
    ) async {
      api.conversations = [
        ConversationView(
          id: 'conv_1',
          title: 'Original Title',
          updatedAt: testNow,
        ),
      ];
      api.searchResults = [
        ConversationSearchResult(
          conversation: ConversationView(
            id: 'conv_1',
            title: 'Found Match',
            updatedAt: testNow,
          ),
          snippet: 'Relevant excerpt from the conversation message…',
          matched: 'content',
        ),
      ];

      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () {}),
      );
      await tester.pump();

      expect(find.text('Original Title'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'Found');
      // Wait for debounce timer (10ms in test)
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pumpAndSettle();

      expect(find.text('Found Match'), findsOneWidget);
      expect(
        find.text('Relevant excerpt from the conversation message…'),
        findsOneWidget,
      );
      expect(find.text('Matched in content'), findsOneWidget);
    });

    testWidgets('delete shows undo snackbar and Undo restores row', (
      tester,
    ) async {
      api.conversations = [
        ConversationView(
          id: 'conv_delete_me',
          title: 'To Be Deleted',
          updatedAt: testNow,
        ),
      ];

      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () {}),
      );
      await tester.pump();

      expect(find.text('To Be Deleted'), findsOneWidget);

      // Open overflow actions menu
      await tester.tap(find.byIcon(Icons.more_vert));
      await tester.pumpAndSettle();

      // Tap Delete in bottom sheet
      expect(find.text('Delete'), findsOneWidget);
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      // Row is removed optimistically and SnackBar is displayed
      expect(find.text('To Be Deleted'), findsNothing);
      expect(find.text('Chat deleted'), findsOneWidget);
      expect(find.text('Undo'), findsOneWidget);

      // Tap Undo
      await tester.tap(find.text('Undo'));
      await tester.pumpAndSettle();

      // Restored row is present again
      expect(find.text('Restored chat'), findsOneWidget);
      expect(api.restoredIds, contains('conv_delete_me'));
    });

    testWidgets('archived toggle switches view', (tester) async {
      api.conversations = [
        ConversationView(
          id: 'conv_active',
          title: 'Active Chat',
          updatedAt: testNow,
        ),
        ConversationView(
          id: 'conv_archived',
          title: 'Archived Chat',
          archivedAt: testNow,
          updatedAt: testNow,
        ),
      ];

      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () {}),
      );
      await tester.pump();

      expect(find.text('Active Chat'), findsOneWidget);
      expect(find.text('Archived Chat'), findsNothing);

      // Tap archived filter chip
      await tester.tap(find.byKey(const ValueKey('archived-filter-chip')));
      await tester.pumpAndSettle();

      expect(controller.showArchived, isTrue);
      expect(find.text('Archived Chat'), findsOneWidget);
      expect(find.text('Active Chat'), findsNothing);
    });

    testWidgets('rename action updates conversation title', (tester) async {
      api.conversations = [
        ConversationView(
          id: 'conv_rename',
          title: 'Old Title',
          updatedAt: testNow,
        ),
      ];

      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () {}),
      );
      await tester.pump();

      // Open overflow actions
      await tester.tap(find.byIcon(Icons.more_vert));
      await tester.pumpAndSettle();

      // Tap Rename
      await tester.tap(find.text('Rename'));
      await tester.pumpAndSettle();

      expect(find.text('Rename conversation'), findsOneWidget);

      // Enter new title
      await tester.enterText(
        find.descendant(
          of: find.byType(AlertDialog),
          matching: find.byType(TextField),
        ),
        'New Exciting Title',
      );
      await tester.pump();

      // Tap Save
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      expect(find.text('New Exciting Title'), findsOneWidget);
    });

    testWidgets('pin action toggles pinned status', (tester) async {
      api.conversations = [
        ConversationView(
          id: 'conv_pin',
          title: 'Pin Me',
          pinned: false,
          updatedAt: testNow,
        ),
      ];

      await controller.refresh();
      await tester.pumpWidget(
        buildTestWidget(onOpen: (_) {}, onNewChat: () {}),
      );
      await tester.pump();

      expect(find.byIcon(Icons.push_pin), findsNothing);

      // Open overflow actions
      await tester.tap(find.byIcon(Icons.more_vert));
      await tester.pumpAndSettle();

      // Tap Pin
      await tester.tap(find.text('Pin'));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.push_pin), findsOneWidget);
    });

    testWidgets('relative date formatting returns readable intervals', (
      WidgetTester tester,
    ) async {
      final now = DateTime.utc(2026, 10, 21, 12, 0, 0);

      expect(
        formatRelativeDate(now.subtract(const Duration(seconds: 30)), now),
        'Just now',
      );
      expect(
        formatRelativeDate(now.subtract(const Duration(minutes: 5)), now),
        '5m ago',
      );
      expect(
        formatRelativeDate(now.subtract(const Duration(hours: 3)), now),
        '3h ago',
      );
      expect(
        formatRelativeDate(now.subtract(const Duration(days: 4)), now),
        '4d ago',
      );
      expect(formatRelativeDate(DateTime.utc(2026, 9, 1), now), '2026-09-01');
    });
  });

  group('SearchField', () {
    testWidgets('shows clear button and clears on tap', (tester) async {
      String lastQuery = '';
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SearchField(onChanged: (val) => lastQuery = val),
          ),
        ),
      );

      expect(find.byIcon(Icons.clear), findsNothing);

      await tester.enterText(find.byType(TextField), 'karmi');
      await tester.pump();

      expect(find.byIcon(Icons.clear), findsOneWidget);
      expect(lastQuery, 'karmi');

      await tester.tap(find.byIcon(Icons.clear));
      await tester.pump();

      expect(find.byIcon(Icons.clear), findsNothing);
      expect(lastQuery, '');
    });
  });
}
