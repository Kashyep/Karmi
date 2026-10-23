import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/features/chat/empty_state.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/shell/bottom_chrome.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class _FakeRunStreamClient extends RunStreamClient {
  _FakeRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? _activeRunController;
  int startRunCalls = 0;
  int startCalls = 0;
  int resumeCalls = 0;
  int continueCalls = 0;
  StreamController<RunEvent>? _resumeController;
  StreamController<RunEvent>? _continueController;

  @override
  Stream<RunEvent> resumeRun({required String runId, required int afterSeq}) {
    resumeCalls++;
    _resumeController = StreamController<RunEvent>.broadcast();
    return _resumeController!.stream;
  }

  @override
  Stream<RunEvent> startRun({
    required String text,
    String? conversationId,
    required String clientMessageId,
  }) {
    startRunCalls++;
    startCalls++;
    _activeRunController = StreamController<RunEvent>.broadcast();
    return _activeRunController!.stream;
  }

  @override
  Stream<RunEvent> continueMessage(String assistantMessageId) {
    continueCalls++;
    _continueController = StreamController<RunEvent>.broadcast();
    return _continueController!.stream;
  }

  void emitStarted() {
    _activeRunController?.add(
      const RunStartedEvent(
        runId: 'run-1',
        conversationId: 'conv-1',
        userMessageId: 'user-1',
        assistantMessageId: 'asst-1',
      ),
    );
  }

  void emit(RunEvent event) => _activeRunController?.add(event);

  void emitError(RunStreamException error) =>
      _activeRunController?.addError(error);
}

class _FakeConversationsApi implements ConversationsApi {
  int requestCount = 0;
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
    requestCount++;
    return const ConversationPage(items: [], nextCursor: null);
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    requestCount++;
    return const MessagePage(items: [], hasMoreBefore: false);
  }

  @override
  Future<ConversationView> get(String id) async {
    requestCount++;
    throw UnimplementedError();
  }

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
  }) async {
    requestCount++;
    return [];
  }
}

Widget _wrapWithApp({
  required Widget child,
  bool reduceMotion = false,
  double textScale = 1.0,
}) {
  return LiquidGlassWidgets.wrap(
    child: KarmiAccessibility(
      reduceMotion: reduceMotion,
      reduceTransparency: false,
      child: MaterialApp(
        theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
        home: Builder(
          builder: (context) => MediaQuery(
            // Copy the real view metrics: a bare MediaQueryData has a zero size,
            // which would collapse the screen-relative dock padding.
            data: MediaQuery.of(context).copyWith(
              disableAnimations: reduceMotion,
              textScaler: TextScaler.linear(textScale),
            ),
            child: Scaffold(body: child),
          ),
        ),
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ChatEmptyState greeting and starter prompts', () {
    testWidgets('Case 1: Greeting by hour renders correct greeting strings', (
      tester,
    ) async {
      // 08:00 -> 'Good morning'
      await tester.pumpWidget(
        _wrapWithApp(
          child: ChatEmptyState(
            onStarterPicked: (_) {},
            clock: () => DateTime(2026, 1, 1, 8),
          ),
        ),
      );
      expect(find.text('Good morning'), findsOneWidget);
      expect(find.textContaining('Ask a study question'), findsOneWidget);
      expect(
        find.text('Ask a study question, or get help with maths or code.'),
        findsOneWidget,
      );

      // 14:00 -> 'Good afternoon'
      await tester.pumpWidget(
        _wrapWithApp(
          child: ChatEmptyState(
            onStarterPicked: (_) {},
            clock: () => DateTime(2026, 1, 1, 14),
          ),
        ),
      );
      expect(find.text('Good afternoon'), findsOneWidget);

      // 20:00 -> 'Good evening'
      await tester.pumpWidget(
        _wrapWithApp(
          child: ChatEmptyState(
            onStarterPicked: (_) {},
            clock: () => DateTime(2026, 1, 1, 20),
          ),
        ),
      );
      expect(find.text('Good evening'), findsOneWidget);

      // Midnight (00:00) -> 'Good evening'
      await tester.pumpWidget(
        _wrapWithApp(
          child: ChatEmptyState(
            onStarterPicked: (_) {},
            clock: () => DateTime(2026, 1, 1, 0),
          ),
        ),
      );
      expect(find.text('Good evening'), findsOneWidget);

      // Personalized with name
      await tester.pumpWidget(
        _wrapWithApp(
          child: ChatEmptyState(
            onStarterPicked: (_) {},
            clock: () => DateTime(2026, 1, 1, 8),
            name: 'Rosso',
          ),
        ),
      );
      expect(find.text('Good morning, Rosso'), findsOneWidget);
    });

    testWidgets(
      'Case 2: exactly 4 starter chips found and tap invokes onStarterPicked',
      (tester) async {
        String? tappedPrompt;
        await tester.pumpWidget(
          _wrapWithApp(
            child: ChatEmptyState(
              onStarterPicked: (prompt) => tappedPrompt = prompt,
              clock: () => DateTime(2026, 1, 1, 8),
            ),
          ),
        );

        // Verify the const starterPrompts list has exactly 4 items
        expect(ChatEmptyState.starterPrompts.length, 4);

        // Verify all 4 prompts are rendered
        for (final prompt in ChatEmptyState.starterPrompts) {
          expect(find.text(prompt), findsOneWidget);
        }

        // Verify chips have button semantics
        final chipButtons = find.byWidgetPredicate(
          (widget) =>
              widget is Semantics &&
              widget.properties.button == true &&
              ChatEmptyState.starterPrompts.contains(widget.properties.label),
        );
        expect(chipButtons, findsNWidgets(4));

        // Tap one of the chips
        const targetPrompt = 'Review my code for bugs';
        await tester.tap(find.text(targetPrompt));
        await tester.pump();

        expect(tappedPrompt, equals(targetPrompt));
      },
    );
    testWidgets(
      'Case 2b: tapping a chip sends no request and fills composer with starter and topic cursor',
      (tester) async {
        final fakeStream = _FakeRunStreamClient();
        final controller = ChatController(
          client: fakeStream,
          deltaFlushInterval: Duration.zero,
        );
        final fakeConversations = _FakeConversationsApi();
        final convController = ConversationListController(
          api: fakeConversations,
        );

        await tester.pumpWidget(
          _wrapWithApp(
            reduceMotion: false,
            child: ChatScreen(
              api: KarmiApi(baseUrl: 'http://fake.test'),
              chatController: controller,
              conversationListController: convController,
              clock: () => DateTime(2026, 1, 1, 10),
            ),
          ),
        );
        await tester.pump();

        final runsBefore = fakeStream.startRunCalls;
        final apiBefore = fakeConversations.requestCount;

        // Tap the 'Explain a concept step by step' suggestion chip
        await tester.tap(find.text('Explain a concept step by step'));
        await tester.pump();

        // Zero run-stream and conversation API requests after the tap
        expect(fakeStream.startRunCalls, equals(runsBefore));
        expect(fakeConversations.requestCount, equals(apiBefore));

        // Empty state remains visible (not transitioned to transcript)
        expect(
          find.byKey(const ValueKey('new-chat-empty-state')),
          findsOneWidget,
        );

        // Composer field contains starter template with cursor placed at topic slot
        final textField = tester.widget<TextField>(find.byType(TextField));
        expect(textField.controller!.text, equals('Explain  step by step'));
        expect(
          textField.controller!.selection,
          equals(const TextSelection.collapsed(offset: 8)),
        );
        expect(textField.focusNode!.hasFocus, isTrue);

        // Tap another chip to verify it updates the template and cursor position
        await tester.tap(find.text('Review my code for bugs'));
        await tester.pump();

        expect(fakeStream.startRunCalls, equals(runsBefore));
        expect(fakeConversations.requestCount, equals(apiBefore));
        expect(textField.controller!.text, equals('Review  for bugs'));
        expect(
          textField.controller!.selection,
          equals(const TextSelection.collapsed(offset: 7)),
        );
        expect(textField.focusNode!.hasFocus, isTrue);

        // Unmount to dispose controllers cleanly
        await tester.pumpWidget(const SizedBox.shrink());
        controller.dispose();
        convController.dispose();
      },
    );
  });

  composerTests();
}

class _ChatHarness {
  _ChatHarness(this.stream, this.controller, this.convController);

  final _FakeRunStreamClient stream;
  final ChatController controller;
  final ConversationListController convController;

  void dispose() {
    controller.dispose();
    convController.dispose();
  }
}

Future<_ChatHarness> _pumpChat(
  WidgetTester tester, {
  bool reduceMotion = false,
  double textScale = 1.0,
  double bottomInset = 0,
  double devicePixelRatio = 1.0,
  int maxResumeRetries = 3,
}) async {
  tester.view.devicePixelRatio = devicePixelRatio;
  addTearDown(tester.view.resetDevicePixelRatio);
  tester.view.viewInsets = FakeViewPadding(bottom: bottomInset);
  addTearDown(tester.view.resetViewInsets);

  final stream = _FakeRunStreamClient();
  final controller = ChatController(
    client: stream,
    deltaFlushInterval: Duration.zero,
    maxResumeRetries: maxResumeRetries,
  );
  final convController = ConversationListController(
    api: _FakeConversationsApi(),
  );
  await tester.pumpWidget(
    _wrapWithApp(
      reduceMotion: reduceMotion,
      textScale: textScale,
      child: ChatScreen(
        api: KarmiApi(baseUrl: 'http://fake.test'),
        chatController: controller,
        conversationListController: convController,
        clock: () => DateTime(2026, 1, 1, 10),
      ),
    ),
  );
  await tester.pump();
  return _ChatHarness(stream, controller, convController);
}

Future<void> _sendText(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byKey(const ValueKey('composer-send-button')));
  await tester.pump();
}

Future<void> _unmount(WidgetTester tester, _ChatHarness harness) async {
  await tester.pumpWidget(const SizedBox.shrink());
  harness.dispose();
}

bool _composerFocused(WidgetTester tester) =>
    tester.widget<TextField>(find.byType(TextField)).focusNode!.hasFocus;

RunStreamException _providerDown() => const RunStreamException(
  category: ErrorCategory.providerUnavailable,
  message: 'down',
);

void composerTests() {
  group('ChatScreen composer never moves', () {
    for (final reduceMotion in [false, true]) {
      for (final bottomInset in [0.0, 300.0]) {
        for (final textScale in [1.0, 2.0]) {
          testWidgets(
            'composer rect is identical across empty, pending, reply and error '
            '(reduceMotion: $reduceMotion, inset: $bottomInset, textScale: $textScale)',
            (tester) async {
              final h = await _pumpChat(
                tester,
                reduceMotion: reduceMotion,
                textScale: textScale,
                bottomInset: bottomInset,
              );
              final surface = find.byKey(const ValueKey('composer-surface'));
              final screenHeight =
                  tester.view.physicalSize.height /
                  tester.view.devicePixelRatio;

              expect(
                find.byKey(const ValueKey('new-chat-empty-state')),
                findsOneWidget,
              );
              final emptyRect = tester.getRect(surface);
              // Bottom-docked above the keyboard inset, even on an empty chat.
              expect(
                emptyRect.bottom,
                lessThanOrEqualTo(screenHeight - bottomInset),
              );
              expect(
                screenHeight - bottomInset - emptyRect.bottom,
                lessThan(120.0),
              );

              // Pending: sent, no reply yet.
              await _sendText(tester, 'Explain gravity');
              expect(tester.getRect(surface), emptyRect);

              // Streaming, then a failed reply: the error sits on the placeholder.
              h.stream.emitStarted();
              await tester.pump();
              expect(tester.getRect(surface), emptyRect);
              h.stream.emit(
                const RunErrorEvent(
                  category: ErrorCategory.providerUnavailable,
                  retryable: true,
                  assistantMessageId: 'asst-1',
                ),
              );
              await tester.pumpAndSettle();
              expect(find.text('Retry'), findsOneWidget);
              expect(
                find.byKey(const ValueKey('new-chat-empty-state')),
                findsNothing,
              );
              expect(tester.getRect(surface), emptyRect);

              await _unmount(tester, h);
            },
          );
        }
      }
    }
  });

  group('ChatScreen honest status', () {
    testWidgets('keyboard inset stays in logical units at 2x DPR', (
      tester,
    ) async {
      final h = await _pumpChat(tester, devicePixelRatio: 2, bottomInset: 150);
      final screenHeight =
          tester.view.physicalSize.height / tester.view.devicePixelRatio;
      final composer = tester.getRect(
        find.byKey(const ValueKey('composer-surface')),
      );
      // FakeViewPadding is expressed in view pixels; MediaQuery converts it
      // to 75 logical pixels at 2x. Multiplying it again would move the dock
      // far too high and violate this screen-relative gap.
      expect(screenHeight - composer.bottom, lessThan(120));
      await _unmount(tester, h);
    });

    testWidgets('after 10 s with no reply the placeholder says still working', (
      tester,
    ) async {
      final h = await _pumpChat(tester);
      await _sendText(tester, 'Slow one');
      h.stream.emitStarted();
      await tester.pump();

      expect(find.text('Working…'), findsOneWidget);
      expect(find.text('Still working, Karmi can be slow'), findsNothing);

      await tester.pump(const Duration(seconds: 10));
      expect(find.text('Still working, Karmi can be slow'), findsOneWidget);

      await _unmount(tester, h);
    });

    testWidgets(
      'error attaches to the placeholder bubble with a working Retry',
      (tester) async {
        final h = await _pumpChat(tester);
        await _sendText(tester, 'Will fail');
        h.stream.emitStarted();
        await tester.pump();

        h.stream.emit(
          const RunErrorEvent(
            category: ErrorCategory.providerUnavailable,
            retryable: true,
            assistantMessageId: 'asst-1',
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('The model service had a problem.'), findsOneWidget);
        expect(find.text('Working…'), findsNothing);
        expect(h.controller.messages.last.status, MessageStatus.failed);

        await tester.tap(find.text('Retry'));
        await tester.pump();
        await tester.pump();
        expect(h.stream.startCalls, 1);
        expect(h.stream.continueCalls, 1);

        await _unmount(tester, h);
      },
    );

    testWidgets('deferred finish is shown as an error with Retry', (
      tester,
    ) async {
      final h = await _pumpChat(tester);
      await _sendText(tester, 'Deferred one');
      h.stream.emitStarted();
      await tester.pump();

      h.stream.emit(
        const RunFinishedEvent(
          finishReason: FinishReason.stop,
          outcome: 'DEFERRED',
          assistantMessageId: 'asst-1',
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('The model service had a problem.'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      expect(h.controller.phase, ChatRunPhase.error);

      await _unmount(tester, h);
    });

    testWidgets('a stream timeout says taking too long, not offline', (
      tester,
    ) async {
      final h = await _pumpChat(tester, maxResumeRetries: 0);
      await _sendText(tester, 'Timeout one');
      h.stream.emitStarted();
      await tester.pump();

      h.stream.emitError(
        const RunStreamException(category: ErrorCategory.timeout),
      );
      await tester.pumpAndSettle(const Duration(seconds: 10));

      expect(find.text('Karmi is taking too long, try again'), findsOneWidget);
      expect(find.text('You appear to be offline.'), findsNothing);

      await _unmount(tester, h);
    });

    testWidgets('a network error still says offline', (tester) async {
      final h = await _pumpChat(tester);
      await _sendText(tester, 'Offline one');
      h.stream.emitStarted();
      await tester.pump();

      h.stream.emit(
        const RunErrorEvent(
          category: ErrorCategory.network,
          retryable: true,
          assistantMessageId: 'asst-1',
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('You appear to be offline.'), findsOneWidget);

      await _unmount(tester, h);
    });

    testWidgets(
      'keyboard is dismissed after a send and restored after an error',
      (tester) async {
        final h = await _pumpChat(tester);
        await tester.tap(find.byType(TextField));
        await tester.pump();
        expect(_composerFocused(tester), isTrue);

        await _sendText(tester, 'Focus check');
        expect(_composerFocused(tester), isFalse);

        h.stream.emitStarted();
        await tester.pump();
        h.stream.emitError(_providerDown());
        await tester.pumpAndSettle(const Duration(seconds: 10));
        expect(_composerFocused(tester), isTrue);

        await _unmount(tester, h);
      },
    );

    testWidgets('BottomChrome publishes the measured composer dock height', (
      tester,
    ) async {
      final h = await _pumpChat(tester);
      final dock = tester.getRect(
        find.byKey(const ValueKey('chat-composer-dock')),
      );
      expect(BottomChrome.composerHeight, closeTo(dock.height, 0.5));

      await _unmount(tester, h);
      BottomChrome.composerHeight = 0;
    });
  });
}
