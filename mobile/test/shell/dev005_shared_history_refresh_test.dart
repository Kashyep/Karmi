// DEV-005 regression test: shared ConversationListController is refreshed
// in the history drawer/rail when a new chat run starts and when it finishes.
//
// Mutation proof: removing `conversationListController:
// widget.conversationListController` from KarmiShell._buildPage causes
// ChatScreen to create an isolated (unshared) controller that never refreshes
// the drawer's ConversationList. The test fails because the drawer does not
// receive the refresh signal and the new conversation title is absent.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/history/conversation_list.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/features/welcome/tester_notice.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/shell/chat_history_commands.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:karmi_app/theme/karmi_glass.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

// ---------------------------------------------------------------------------
// Fake conversations API that tracks `list` calls and allows the caller to
// inject different conversation lists across successive refreshes.
// ---------------------------------------------------------------------------

class _TrackingConversationsApi implements ConversationsApi {
  _TrackingConversationsApi({required this.responsesByCalls});

  /// Successive responses returned on each `list` call. The last entry is
  /// repeated once exhausted.
  final List<List<ConversationView>> responsesByCalls;
  int listCallCount = 0;

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
    final idx = listCallCount < responsesByCalls.length
        ? listCallCount
        : responsesByCalls.length - 1;
    listCallCount++;
    return ConversationPage(items: responsesByCalls[idx], nextCursor: null);
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async => MessagePage(items: [], hasMoreBefore: false);

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

// ---------------------------------------------------------------------------
// SSE helpers
// ---------------------------------------------------------------------------

String _sseRunStarted(String convId) =>
    'event: run.started\n'
    'data: {"run_id":"run-new","conversation_id":"$convId",'
    '"user_message_id":"msg-u","assistant_message_id":"msg-a","seq":0}\n\n'
    'id: 1\n'
    'event: message.delta\n'
    'data: {"text":"Hello from Karmi!"}\n\n'
    'event: run.finished\n'
    'data: {"finish_reason":"stop","outcome":"success"}\n\n';

// ---------------------------------------------------------------------------
// Pump helper: builds KarmiShell at phone width with the shared controller
// ---------------------------------------------------------------------------

Future<_TestHandles> _pumpShell(
  WidgetTester tester, {
  required _TrackingConversationsApi convApi,
  required String sseConversationId,
  Size size = const Size(400, 800),
  EdgeInsets? padding,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({
    'has_completed_onboarding': true,
    'dev_session_token': 'test-token',
    'notification_permission_requested': true,
    'armory_unlocked_tier': 1,
    'armory_active_theme': 1,
    'acknowledged_tester_notice_version': kTesterNoticeVersion,
  });
  final prefs = await SharedPreferences.getInstance();
  final settings = KarmiSettings(prefs);

  // HTTP client: routes /v1/chat/stream as SSE; everything else is a stub.
  final httpClient = MockClient((req) async {
    final path = req.url.path;
    if (path == '/v1/chat/stream' && req.method == 'POST') {
      return http.Response(
        _sseRunStarted(sseConversationId),
        200,
        headers: {'content-type': 'text/event-stream'},
      );
    }
    if (path == '/v1/armory' && req.method == 'GET') {
      return http.Response(
        '{"unlocked_tier":1,"active_theme":1,"tiers":['
        '{"id":1,"key":"ananta","label":"Ananta","plan_id":"ananta"}]}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response(
      '{"items":[],"next_cursor":null}',
      200,
      headers: {'content-type': 'application/json'},
    );
  });

  final api = KarmiApi(
    baseUrl: 'http://karmi.test',
    client: httpClient,
    token: 'test-token',
  );
  final session = KarmiSession(api: api, prefs: prefs);
  final armory = ArmoryController(
    api: api,
    prefs: prefs,
    appIcon: FakeAppIcons(),
  );
  addTearDown(armory.dispose);

  final convController = ConversationListController(api: convApi);
  addTearDown(convController.dispose);
  // Initial load – call 0.
  await convController.refresh();

  final commands = ChatHistoryCommands();
  addTearDown(commands.dispose);

  await tester.pumpWidget(
    LiquidGlassWidgets.wrap(
      theme: KarmiGlass.themeData(armory.effectiveTier),
      brightnessResolver: Theme.maybeBrightnessOf,
      adaptiveQuality: false,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: KarmiTheme.of(armory.effectiveTier, Brightness.light),
        builder: padding != null
            ? (context, child) => MediaQuery(
                data: MediaQuery.of(context).copyWith(padding: padding),
                child: child!,
              )
            : null,
        home: KarmiShell(
          api: api,
          settings: settings,
          session: session,
          armory: armory,
          historyCommands: commands,
          conversationListController: convController,
          clock: () => FakeBackend.pinnedNow,
          historyRailBuilder: (context) => ValueListenableBuilder<String?>(
            valueListenable: commands.activeId,
            builder: (_, activeId, __) => ConversationList(
              controller: convController,
              activeConversationId: activeId,
              clock: () => FakeBackend.pinnedNow,
              onOpen: (id) => commands.openConversation?.call(id),
              onNewChat: () => commands.newChat?.call(),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 500));

  return _TestHandles(
    convController: convController,
    convApi: convApi,
    commands: commands,
  );
}

class _TestHandles {
  _TestHandles({
    required this.convController,
    required this.convApi,
    required this.commands,
  });
  final ConversationListController convController;
  final _TrackingConversationsApi convApi;
  final ChatHistoryCommands commands;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final initialConversations = <ConversationView>[];

  final newConversation = ConversationView(
    id: 'conv-new',
    title: 'Fresh start',
    updatedAt: FakeBackend.pinnedNow,
  );

  // The tracking API returns [] on call 0 (initial load), then returns
  // [newConversation] on every subsequent call (after the run triggers refresh).
  _TrackingConversationsApi buildConvApi() => _TrackingConversationsApi(
    responsesByCalls: [
      initialConversations, // call 0: initial load → empty
      [newConversation], // call 1: refresh at run.started
      [newConversation], // call 2: refresh at run.finished
    ],
  );

  testWidgets(
    'DEV-005 (a): shared ConversationListController is refreshed after a new '
    'chat run completes, and the new conversation appears in the history drawer',
    (tester) async {
      final convApi = buildConvApi();
      final handles = await _pumpShell(
        tester,
        convApi: convApi,
        sseConversationId: 'conv-new',
      );

      // Initial state: list was loaded once (call 0) during setup.
      final callsAfterInit = handles.convApi.listCallCount;
      expect(
        callsAfterInit,
        1,
        reason: 'initial refresh() should produce exactly 1 list call',
      );
      expect(
        handles.convController.conversations,
        isEmpty,
        reason: 'initially no conversations',
      );

      // ---- Send a message ------------------------------------------------
      // The ChatScreen is already on tab 0 as the first page.
      final sendField = find.byType(TextField);
      expect(sendField, findsOneWidget);
      await tester.enterText(sendField, 'Hello!');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));

      // Let the SSE stream deliver run.started → run.finished.
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 200));

      // ---- Verify shared controller was refreshed -------------------------
      // At minimum, the shared controller must have been refreshed at least
      // once after the initial load: either at run.started (conversationId set)
      // or at run.finished (phase transition).
      expect(
        handles.convApi.listCallCount,
        greaterThan(callsAfterInit),
        reason:
            'ChatScreen must call conversationListController.refresh() after '
            'the run so the shared drawer/rail controller picks up the new '
            'conversation. If this fails, the fix in KarmiShell._buildPage '
            '(conversationListController: widget.conversationListController) '
            'and/or _onChatControllerChanged (refresh on finished) is missing.',
      );
      expect(
        handles.convController.conversations,
        contains(
          predicate<ConversationView>(
            (c) => c.id == 'conv-new' && c.title == 'Fresh start',
            'has conv-new with title Fresh start',
          ),
        ),
        reason:
            'After the run, the shared ConversationListController must hold '
            'the newly created conversation so the drawer/rail renders it.',
      );

      // ---- Open drawer and confirm the conversation is listed -------------
      final historyBtn = find.byKey(const ValueKey('chat-header-history'));
      expect(historyBtn, findsOneWidget);
      await tester.tap(historyBtn);
      await tester.pump(const Duration(milliseconds: 400));

      expect(
        find.text('Fresh start'),
        findsWidgets,
        reason:
            'The new conversation title must appear in the history drawer '
            'without an app restart.',
      );
    },
  );

  testWidgets(
    'DEV-005 (b): refresh fires specifically when run.finished phase is reached '
    '(not only at run.started / conversationId set)',
    (tester) async {
      // This test uses a custom ConversationListController to count refreshes
      // at a finer grain.
      final convApi = buildConvApi();
      final handles = await _pumpShell(
        tester,
        convApi: convApi,
        sseConversationId: 'conv-new',
      );

      final callsBeforeSend = handles.convApi.listCallCount;

      final sendField = find.byType(TextField);
      await tester.enterText(sendField, 'Test message');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));

      // Pump through run.started (should trigger 1 refresh) and run.finished
      // (should trigger a second refresh).
      await tester.pump(const Duration(milliseconds: 300));

      final callsAfterRun = handles.convApi.listCallCount;
      // We expect at least 2 more calls: one for run.started, one for
      // run.finished. The exact number is ≥ 2.
      expect(
        callsAfterRun - callsBeforeSend,
        greaterThanOrEqualTo(2),
        reason:
            'Expected ≥ 2 refresh calls after a complete run: once when '
            'conversationId is first set (run.started) and once when phase '
            'transitions to finished (run.finished). Got '
            '${callsAfterRun - callsBeforeSend}.',
      );
    },
  );

  testWidgets(
    'DEV-006: landscape with left safe-area cutout keeps all 4 NavigationRail destinations visible and unclipped',
    (tester) async {
      final convApi = buildConvApi();
      await _pumpShell(
        tester,
        convApi: convApi,
        sseConversationId: 'conv-new',
        size: const Size(915, 412),
        padding: const EdgeInsets.only(left: 52, top: 24, bottom: 24),
      );

      final railFinder = find.byType(NavigationRail);
      expect(railFinder, findsOneWidget);

      for (final label in ['Chat', 'Tasks', 'Usage', 'Settings']) {
        final dest = find.descendant(
          of: railFinder,
          matching: find.text(label),
        );
        expect(dest, findsOneWidget, reason: 'Destination $label should exist');
        final rect = tester.getRect(dest);
        expect(
          rect.height,
          greaterThan(0),
          reason: '$label height should be positive',
        );
        expect(
          rect.height,
          lessThan(30),
          reason:
              '$label should be a single line (not wrapped 1-char-per-line)',
        );
        expect(
          rect.bottom,
          lessThanOrEqualTo(412),
          reason: '$label should be visible and not pushed off screen',
        );
      }
    },
  );
}
