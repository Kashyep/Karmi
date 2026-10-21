import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/features/history/conversation_list.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/shell/chat_history_commands.dart';
import 'package:karmi_app/shell/history_panel.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class _FakeConversationsApi implements ConversationsApi {
  _FakeConversationsApi({
    this.conversations = const [],
    this.messageItems = const [],
  });

  final List<ConversationView> conversations;
  final List<ChatMessageView> messageItems;
  final List<String> callLog = [];

  @override
  String baseUrl = 'http://fake.test';

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
    callLog.add('list');
    return ConversationPage(items: conversations, nextCursor: null);
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    callLog.add('messages:$id');
    return MessagePage(items: messageItems, hasMoreBefore: false);
  }

  @override
  Future<ConversationView> get(String id) async => throw UnimplementedError();

  @override
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async => throw UnimplementedError();

  @override
  Future<void> delete(String id) async => throw UnimplementedError();

  @override
  Future<ConversationView> restore(String id) async =>
      throw UnimplementedError();

  @override
  Future<List<ConversationSearchResult>> search(
    String q, {
    int limit = 20,
  }) async => [];
}

class _PhoneWiringHarness extends StatefulWidget {
  const _PhoneWiringHarness({
    required this.commands,
    required this.convController,
    required this.convApi,
  });

  final ChatHistoryCommands commands;
  final ConversationListController convController;
  final ConversationsApi convApi;

  @override
  State<_PhoneWiringHarness> createState() => _PhoneWiringHarnessState();
}

class _PhoneWiringHarnessState extends State<_PhoneWiringHarness> {
  final _scaffoldKey = GlobalKey<ScaffoldState>();

  void _openHistory() {
    _scaffoldKey.currentState?.openDrawer();
  }

  @override
  Widget build(BuildContext context) {
    return LiquidGlassWidgets.wrap(
      child: MaterialApp(
        theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
        home: HistoryPanelScope(
          isOpen: false,
          openHistory: _openHistory,
          closeHistory: () {},
          toggleHistory: () {},
          child: Scaffold(
            key: _scaffoldKey,
            drawer: HistoryDrawer(
              child: Builder(
                builder: (innerContext) => ValueListenableBuilder<String?>(
                  valueListenable: widget.commands.activeId,
                  builder: (_, activeId, __) => ConversationList(
                    controller: widget.convController,
                    activeConversationId: activeId,
                    onOpen: (id) {
                      widget.commands.openConversation?.call(id);
                      HistoryPanelScope.maybeOf(innerContext)?.closeHistory();
                      final scaffold = Scaffold.maybeOf(innerContext);
                      if (scaffold != null && scaffold.isDrawerOpen) {
                        scaffold.closeDrawer();
                      }
                    },
                    onNewChat: () {
                      widget.commands.newChat?.call();
                      HistoryPanelScope.maybeOf(innerContext)?.closeHistory();
                      final scaffold = Scaffold.maybeOf(innerContext);
                      if (scaffold != null && scaffold.isDrawerOpen) {
                        scaffold.closeDrawer();
                      }
                    },
                  ),
                ),
              ),
            ),
            body: ChatScreen(
              api: KarmiApi(baseUrl: 'http://fake.test'),
              historyCommands: widget.commands,
              conversationsApi: widget.convApi,
              conversationListController: widget.convController,
            ),
          ),
        ),
      ),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    '(a) phone width: opening drawer and tapping a conversation calls openConversation and loads it',
    (tester) async {
      tester.view.physicalSize = const Size(400, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      final commands = ChatHistoryCommands();
      addTearDown(commands.dispose);

      final fakeApi = _FakeConversationsApi(
        conversations: [
          ConversationView(
            id: 'conv-42',
            title: 'Project Roadmap',
            updatedAt: DateTime.utc(2026, 10, 20),
          ),
        ],
        messageItems: [
          ChatMessageView(
            id: 'msg-1',
            conversationId: 'conv-42',
            role: 'assistant',
            status: MessageStatus.complete,
            content: 'Roadmap loaded successfully',
            createdAt: DateTime.utc(2026, 10, 20),
            updatedAt: DateTime.utc(2026, 10, 20),
          ),
        ],
      );
      final convController = ConversationListController(api: fakeApi);
      await convController.refresh();
      addTearDown(convController.dispose);

      await tester.pumpWidget(
        _PhoneWiringHarness(
          commands: commands,
          convController: convController,
          convApi: fakeApi,
        ),
      );
      await tester.pumpAndSettle();

      // Tap history icon to open drawer
      final historyBtn = find.byKey(const ValueKey('chat-header-history'));
      expect(historyBtn, findsOneWidget);
      await tester.tap(historyBtn);
      await tester.pumpAndSettle();

      // Drawer is open, conversation is visible
      final convItem = find.text('Project Roadmap');
      expect(convItem, findsOneWidget);

      // Tap conversation
      await tester.tap(convItem);
      await tester.pumpAndSettle();

      // Check openConversation loaded messages and updated commands & UI
      expect(fakeApi.callLog.contains('messages:conv-42'), isTrue);
      expect(commands.activeId.value, 'conv-42');
      expect(find.textContaining('Roadmap loaded successfully'), findsOneWidget);
      expect(find.text('Project Roadmap'), findsOneWidget);
    },
  );

  testWidgets('(b) New chat from the drawer resets the ChatScreen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final commands = ChatHistoryCommands(activeConversationId: 'conv-42');
    addTearDown(commands.dispose);

    final fakeApi = _FakeConversationsApi(
      conversations: [
        ConversationView(
          id: 'conv-42',
          title: 'Project Roadmap',
          updatedAt: DateTime.utc(2026, 10, 20),
        ),
      ],
      messageItems: [
        ChatMessageView(
          id: 'msg-1',
          conversationId: 'conv-42',
          role: 'assistant',
          status: MessageStatus.complete,
          content: 'Roadmap loaded successfully',
          createdAt: DateTime.utc(2026, 10, 20),
          updatedAt: DateTime.utc(2026, 10, 20),
        ),
      ],
    );
    final convController = ConversationListController(api: fakeApi);
    await convController.refresh();
    addTearDown(convController.dispose);

    await tester.pumpWidget(
      _PhoneWiringHarness(
        commands: commands,
        convController: convController,
        convApi: fakeApi,
      ),
    );
    await tester.pumpAndSettle();

    // Open drawer
    await tester.tap(find.byKey(const ValueKey('chat-header-history')));
    await tester.pumpAndSettle();

    // Tap New chat button in drawer
    final newChatDrawerBtn = find.byKey(const ValueKey('new-chat-button'));
    expect(newChatDrawerBtn, findsOneWidget);
    await tester.tap(newChatDrawerBtn);
    await tester.pumpAndSettle();

    // Active id should reset to null and transcript to empty state
    expect(commands.activeId.value, isNull);
    expect(find.byKey(const ValueKey('new-chat-empty-state')), findsOneWidget);
    expect(find.text('New chat'), findsWidgets);
  });

  testWidgets(
    '(c) ChatScreen standalone shows KarmiChatHeader with title and New chat button',
    (tester) async {
      await tester.pumpWidget(
        LiquidGlassWidgets.wrap(
          child: MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(
              body: ChatScreen(
                api: KarmiApi(baseUrl: 'http://fake.test'),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('New chat'), findsWidgets);
      final newChatBtn = find.byKey(const ValueKey('chat-header-new-chat'));
      expect(newChatBtn, findsOneWidget);
      expect(find.byTooltip('New chat'), findsOneWidget);
    },
  );
}
