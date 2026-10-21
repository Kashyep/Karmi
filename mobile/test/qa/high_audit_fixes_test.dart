import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/api/errors.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeRunStreamClient extends RunStreamClient {
  _FakeRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? activeRunController;
  final List<Map<String, dynamic>> startRunCalls = [];
  bool stopRunCalled = false;

  @override
  Stream<RunEvent> startRun({
    required String text,
    String? conversationId,
    required String clientMessageId,
  }) {
    startRunCalls.add({
      'text': text,
      'conversationId': conversationId,
      'clientMessageId': clientMessageId,
    });
    activeRunController = StreamController<RunEvent>.broadcast();
    return activeRunController!.stream;
  }

  @override
  Future<void> stopRun(String runId) async {
    stopRunCalled = true;
  }

  void emitStarted() {
    activeRunController?.add(const RunStartedEvent(
      runId: 'run-1',
      conversationId: 'conv-1',
      userMessageId: 'user-1',
      assistantMessageId: 'asst-1',
    ));
  }

  void emitDelta(String text) {
    activeRunController?.add(MessageDeltaEvent(text: text));
  }

  void emitFinished({FinishReason finishReason = FinishReason.stop}) {
    activeRunController?.add(RunFinishedEvent(finishReason: finishReason));
    activeRunController?.close();
  }
}

class _FakeConversationsApi implements ConversationsApi {
  _FakeConversationsApi({
    this.conversations = const [],
    this.messageItems = const [],
    this.throwOnMessages = false,
  });

  final List<ConversationView> conversations;
  final List<ChatMessageView> messageItems;
  bool throwOnMessages;
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
  Future<ConversationPage> list({bool archived = false, String? cursor, int limit = 20}) async {
    callLog.add('list');
    return ConversationPage(items: conversations, nextCursor: null);
  }

  @override
  Future<MessagePage> messages(String id, {String? before, int limit = 50}) async {
    callLog.add('messages:$id');
    if (throwOnMessages) {
      throw const ServerException(500);
    }
    return MessagePage(items: messageItems, hasMoreBefore: false);
  }

  @override
  Future<ConversationView> get(String id) async => throw UnimplementedError();

  @override
  Future<ConversationView> update(String id, {String? title, bool? pinned, bool? archived}) async =>
      throw UnimplementedError();

  @override
  Future<void> delete(String id) async => throw UnimplementedError();

  @override
  Future<ConversationView> restore(String id) async => throw UnimplementedError();

  @override
  Future<List<ConversationSearchResult>> search(String q, {int limit = 20}) async => [];
}

Widget _wrap(Widget child) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(body: child),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AUDIT-02: draft scoping and sign-out clearing', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('sign-out clears all draft.v1.* keys while preserving non-draft keys', () async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('other_setting', 'user_preference');

      final store = SharedPrefsDraftStore(prefs: prefs);
      await store.save('new', 'draft for new conversation');
      await store.save('conv-123', 'draft for existing conversation');

      expect(await store.load('new'), 'draft for new conversation');
      expect(await store.load('conv-123'), 'draft for existing conversation');
      expect(prefs.getString('other_setting'), 'user_preference');

      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://fake.test'),
        prefs: prefs,
      );

      await session.signOut();

      // Drafts must be completely cleared after sign-out
      expect(await store.load('new'), isNull);
      expect(await store.load('conv-123'), isNull);

      // Non-draft preferences must remain untouched
      expect(prefs.getString('other_setting'), 'user_preference');
    });

    test('SharedPrefsDraftStore.clearAll clears all draft keys', () async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('draft.v1.one', 'first');
      await prefs.setString('draft.v1.two', 'second');
      await prefs.setString('unrelated', 'keep_me');

      await SharedPrefsDraftStore.clearAllDrafts(prefs);

      expect(prefs.getString('draft.v1.one'), isNull);
      expect(prefs.getString('draft.v1.two'), isNull);
      expect(prefs.getString('unrelated'), 'keep_me');
    });
  });

  group('AUDIT-01: conversation switch cancels owned stream and handles throwing messages()', () {
    testWidgets('switching conversation cancels previous owned stream subscription', (tester) async {
      final fakeStream = _FakeRunStreamClient();
      final fakeConversationsApi = _FakeConversationsApi(
        messageItems: [
          ChatMessageView(
            id: 'loaded-1',
            conversationId: 'conv-2',
            role: 'assistant',
            status: MessageStatus.complete,
            content: 'Loaded messages for conv-2',
            createdAt: DateTime.utc(2026, 10, 20),
            updatedAt: DateTime.utc(2026, 10, 20),
          ),
        ],
      );

      await tester.pumpWidget(
        _wrap(
          ChatScreen(
            api: KarmiApi(baseUrl: 'http://fake.test'),
            runStreamClient: fakeStream,
            conversationsApi: fakeConversationsApi,
            conversationId: null,
          ),
        ),
      );
      await tester.pump();

      // Enter a prompt in the composer and submit to initiate stream on owned controller
      await tester.enterText(find.byType(TextField), 'Test prompt');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();

      expect(fakeStream.activeRunController, isNotNull);
      expect(fakeStream.activeRunController!.hasListener, isTrue);

      fakeStream.emitStarted();
      fakeStream.emitDelta('Partial response');
      await tester.pump(const Duration(milliseconds: 60));
      expect(find.textContaining('Partial response'), findsOneWidget);

      // Switch to another conversation
      await tester.pumpWidget(
        _wrap(
          ChatScreen(
            api: KarmiApi(baseUrl: 'http://fake.test'),
            runStreamClient: fakeStream,
            conversationsApi: fakeConversationsApi,
            conversationId: 'conv-2',
          ),
        ),
      );
      await tester.pump();

      // The previous stream subscription MUST be cancelled
      expect(fakeStream.activeRunController!.hasListener, isFalse);

      await tester.pumpAndSettle();
      expect(find.textContaining('Loaded messages for conv-2'), findsOneWidget);
    });

    testWidgets('throwing messages() does not leave old controller emitting to UI', (tester) async {
      final fakeStream = _FakeRunStreamClient();
      final fakeConversationsApi = _FakeConversationsApi(throwOnMessages: true);

      await tester.pumpWidget(
        _wrap(
          ChatScreen(
            api: KarmiApi(baseUrl: 'http://fake.test'),
            runStreamClient: fakeStream,
            conversationsApi: fakeConversationsApi,
            conversationId: null,
          ),
        ),
      );
      await tester.pump();

      // Start run on owned controller
      await tester.enterText(find.byType(TextField), 'Hello');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();
      final streamCtrl = fakeStream.activeRunController!;
      expect(streamCtrl.hasListener, isTrue);

      fakeStream.emitStarted();
      fakeStream.emitDelta('Initial tokens');
      await tester.pump(const Duration(milliseconds: 60));

      // Switch to a conversation whose messages fetch will throw an error
      await tester.pumpWidget(
        _wrap(
          ChatScreen(
            api: KarmiApi(baseUrl: 'http://fake.test'),
            runStreamClient: fakeStream,
            conversationsApi: fakeConversationsApi,
            conversationId: 'conv-throwing',
          ),
        ),
      );
      await tester.pump();

      // The old stream subscription must be immediately stopped and cancelled
      expect(streamCtrl.hasListener, isFalse);

      // Settle the throwing messages() fetch
      await tester.pumpAndSettle();

      // Attempting to emit more deltas on the old controller stream produces no UI change
      // and does not throw an unhandled setState on disposed controller
      if (!streamCtrl.isClosed) {
        streamCtrl.add(const MessageDeltaEvent(text: 'Leaked token'));
      }
      await tester.pump(const Duration(milliseconds: 60));

      expect(find.textContaining('Leaked token'), findsNothing);
    });
  });
}
