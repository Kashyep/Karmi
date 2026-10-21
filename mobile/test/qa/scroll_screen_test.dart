import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/features/chat/scroll/end_anchored_scroll.dart';
import 'package:karmi_app/features/chat/scroll/jump_to_latest_button.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class FakeRunStreamClient extends RunStreamClient {
  FakeRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? activeRunController;
  final List<Map<String, dynamic>> startRunCalls = [];

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

  void emitStarted({
    String runId = 'run-1',
    String conversationId = 'conv-1',
    String userMessageId = 'user-1',
    String assistantMessageId = 'asst-1',
  }) {
    activeRunController?.add(RunStartedEvent(
      runId: runId,
      conversationId: conversationId,
      userMessageId: userMessageId,
      assistantMessageId: assistantMessageId,
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
class FakeConversationsApi implements ConversationsApi {
  FakeConversationsApi({this.conversations = const [], this.messageItems = const []});

  final List<ConversationView> conversations;
  final List<ChatMessageView> messageItems;

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
    return ConversationPage(items: conversations, nextCursor: null);
  }

  @override
  Future<MessagePage> messages(String id, {String? before, int limit = 50}) async {
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

Widget wrapChatScreen(Widget child) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(body: child),
    ),
  );
}

ScrollPosition getChatScrollPosition(WidgetTester tester) {
  final listViewFinder = find.descendant(
    of: find.byType(EndAnchoredScroll),
    matching: find.byType(ListView),
  );
  return tester.widget<ListView>(listViewFinder).controller!.position;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ChatScreen scroll pinning and Jump to Latest', () {
    testWidgets(
      '(a) scroll pinning during streaming at chat_screen level: list stays pinned at bottom, '
      'dragged up prevents yank and shows Jump to Latest, tap returns to end and hides button',
      (tester) async {
        final fakeStream = FakeRunStreamClient();
        final controller = ChatController(
          client: fakeStream,
          deltaFlushInterval: const Duration(milliseconds: 10),
        );
        final convController = ConversationListController(api: FakeConversationsApi());

        await tester.pumpWidget(
          wrapChatScreen(
            ChatScreen(
              api: KarmiApi(baseUrl: 'http://fake.test'),
              chatController: controller,
              conversationListController: convController,
            ),
          ),
        );
        await tester.pump();

        // 1. Submit a user message to start streaming.
        await tester.enterText(find.byType(TextField), 'Generate a detailed analysis');
        await tester.pump();
        await tester.tap(find.byTooltip('Send message'));
        await tester.pump();

        fakeStream.emitStarted();
        await tester.pump();

        // 2. Stream tokens to create enough content to overflow the viewport.
        final chunk = 'Line of streaming output for Karmi testing.\n' * 6;
        for (int i = 0; i < 6; i++) {
          fakeStream.emitDelta('Block $i:\n$chunk\n');
          await tester.pump(const Duration(milliseconds: 50));
        }

        // Verify content exceeds viewport and list is pinned at bottom.
        final position = getChatScrollPosition(tester);
        expect(position.maxScrollExtent, greaterThan(150.0));
        expect((position.pixels - position.maxScrollExtent).abs(), lessThanOrEqualTo(1.0));

        // Jump to Latest button should NOT be visible while pinned at the end.
        final jumpBtnFinder = find.byType(JumpToLatestButton);
        expect(jumpBtnFinder, findsOneWidget);
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isFalse);

        // Stream additional tokens while pinned: list stays pinned to bottom.
        final previousMax = position.maxScrollExtent;
        fakeStream.emitDelta('Additional token block while pinned:\n$chunk\n');
        await tester.pump(const Duration(milliseconds: 50));

        expect(position.maxScrollExtent, greaterThan(previousMax));
        expect((position.pixels - position.maxScrollExtent).abs(), lessThanOrEqualTo(1.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isFalse);

        // 3. User drags up (scrolls content down towards history).
        final listFinder = find.descendant(
          of: find.byType(EndAnchoredScroll),
          matching: find.byType(ListView),
        );
        await tester.drag(listFinder, const Offset(0, 300));
        await tester.pump(const Duration(milliseconds: 50));

        // Confirm user is now unpinned and scrolled away from bottom.
        final unpinnedPixels = position.pixels;
        expect(unpinnedPixels, lessThan(position.maxScrollExtent - 48.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isTrue);

        // 4. Stream new tokens while user is scrolled up.
        // New tokens must NOT yank the scroll position.
        final extentBeforeToken = position.maxScrollExtent;
        fakeStream.emitDelta('New tokens arrived while user dragged up:\n$chunk\n');
        await tester.pump(const Duration(milliseconds: 50));

        expect(position.maxScrollExtent, greaterThan(extentBeforeToken));
        expect((position.pixels - unpinnedPixels).abs(), lessThanOrEqualTo(1.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isTrue);

        // Allow button slide/fade-in animation to complete.
        await tester.pump(const Duration(milliseconds: 250));
        expect(find.byType(JumpToLatestButton).hitTestable(), findsOneWidget);
        // 5. Tapping Jump to Latest returns to end and hides the button.
        await tester.tap(jumpBtnFinder);
        for (int i = 0; i < 10; i++) {
          await tester.pump(const Duration(milliseconds: 30));
        }
        expect((position.pixels - position.maxScrollExtent).abs(), lessThanOrEqualTo(1.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isFalse);
        await tester.pump(const Duration(milliseconds: 150));
        expect(find.byType(JumpToLatestButton).hitTestable(), findsNothing);

        fakeStream.emitFinished();
        await tester.pump(const Duration(milliseconds: 50));
      },
    );

    testWidgets(
      '(b) Jump to Latest at screen level: button appears only when unpinned, '
      'has a Semantics label, and tap scrolls to end',
      (tester) async {
        final fakeStream = FakeRunStreamClient();
        final controller = ChatController(
          client: fakeStream,
          deltaFlushInterval: const Duration(milliseconds: 10),
        );
        final convController = ConversationListController(api: FakeConversationsApi());

        await tester.pumpWidget(
          wrapChatScreen(
            ChatScreen(
              api: KarmiApi(baseUrl: 'http://fake.test'),
              chatController: controller,
              conversationListController: convController,
            ),
          ),
        );
        await tester.pump();

        // Send a message and stream large content.
        await tester.enterText(find.byType(TextField), 'Long conversation stream');
        await tester.pump();
        await tester.tap(find.byTooltip('Send message'));
        await tester.pump();

        fakeStream.emitStarted();
        final chunk = 'Line of streaming output for Karmi testing.\n' * 6;
        for (int i = 0; i < 6; i++) {
          fakeStream.emitDelta('Block $i:\n$chunk\n');
          await tester.pump(const Duration(milliseconds: 50));
        }
        fakeStream.emitFinished();
        await tester.pump(const Duration(milliseconds: 50));

        final position = getChatScrollPosition(tester);
        final jumpBtnFinder = find.byType(JumpToLatestButton);

        // At end: button is not visible and has no accessible semantics.
        expect((position.pixels - position.maxScrollExtent).abs(), lessThanOrEqualTo(1.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isFalse);
        expect(find.byType(JumpToLatestButton).hitTestable(), findsNothing);
        // Scroll away from bottom (drag down to view history).
        final listFinder = find.descendant(
          of: find.byType(EndAnchoredScroll),
          matching: find.byType(ListView),
        );
        await tester.drag(listFinder, const Offset(0, 350));
        await tester.pump(const Duration(milliseconds: 250));

        // When unpinned: button becomes visible and has Semantics label.
        expect(position.pixels, lessThan(position.maxScrollExtent - 48.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isTrue);
        expect(find.byType(JumpToLatestButton).hitTestable(), findsOneWidget);
        final semanticsFinder = find.descendant(
          of: jumpBtnFinder,
          matching: find.byWidgetPredicate(
            (w) => w is Semantics && w.properties.label == 'Jump to latest message',
          ),
        );
        expect(semanticsFinder, findsOneWidget);
        await tester.tap(jumpBtnFinder);
        for (int i = 0; i < 10; i++) {
          await tester.pump(const Duration(milliseconds: 30));
        }

        // Verifies scroll reached end and button is hidden again.
        expect((position.pixels - position.maxScrollExtent).abs(), lessThanOrEqualTo(1.0));
        expect(tester.widget<JumpToLatestButton>(jumpBtnFinder).visible, isFalse);
        await tester.pump(const Duration(milliseconds: 150));
        expect(find.byType(JumpToLatestButton).hitTestable(), findsNothing);
      },
    );
  });
}
