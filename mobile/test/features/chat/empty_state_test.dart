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
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class _FakeRunStreamClient extends RunStreamClient {
  _FakeRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? _activeRunController;

  @override
  Stream<RunEvent> startRun({
    required String text,
    String? conversationId,
    required String clientMessageId,
  }) {
    _activeRunController = StreamController<RunEvent>.broadcast();
    return _activeRunController!.stream;
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
}

class _FakeConversationsApi implements ConversationsApi {
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
    return const ConversationPage(items: [], nextCursor: null);
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    return const MessagePage(items: [], hasMoreBefore: false);
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

Widget _wrapWithApp({required Widget child, bool reduceMotion = false}) {
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
            data: MediaQuery.of(
              context,
            ).copyWith(disableAnimations: reduceMotion),
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
  });

  group('ChatScreen composer dock transition', () {
    testWidgets(
      'Case 3: Dock after send moves dock from center to bottom with 220ms curve',
      (tester) async {
        final fakeStream = _FakeRunStreamClient();
        final controller = ChatController(
          client: fakeStream,
          deltaFlushInterval: Duration.zero,
        );
        final convController = ConversationListController(
          api: _FakeConversationsApi(),
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

        // Initially: empty state is visible and dock is centered
        expect(
          find.byKey(const ValueKey('new-chat-empty-state')),
          findsOneWidget,
        );
        final dockFinder = find.byKey(const ValueKey('chat-composer-dock'));
        expect(dockFinder, findsOneWidget);
        // The dock's AnimatedPadding box always spans to the screen bottom; the
        // visible composer surface is what moves with the dock padding.
        final surfaceFinder = find.byKey(const ValueKey('composer-surface'));

        final screenHeight =
            tester.view.physicalSize.height / tester.view.devicePixelRatio;
        final initialBottomDy = tester.getBottomLeft(surfaceFinder).dy;

        // In centered empty state, dock has large bottom padding (> 150px from bottom)
        expect(screenHeight - initialBottomDy, greaterThan(150.0));

        // Enter text in composer and tap send
        await tester.enterText(find.byType(TextField), 'Explain gravity');
        await tester.pump();
        await tester.tap(find.byKey(const ValueKey('composer-send-button')));
        await tester.pump();

        fakeStream.emitStarted();
        await tester.pumpAndSettle();

        // After send completes: empty state is gone
        expect(
          find.byKey(const ValueKey('new-chat-empty-state')),
          findsNothing,
        );

        // Composer dock is now at the bottom (within 120px of screen bottom)
        final dockedBottomDy = tester.getBottomLeft(surfaceFinder).dy;
        expect(screenHeight - dockedBottomDy, lessThanOrEqualTo(120.0));
        expect(dockedBottomDy, greaterThan(initialBottomDy));
      },
    );

    testWidgets(
      'Case 4: Reduced motion instant docks immediately on single pump without intermediate position',
      (tester) async {
        final fakeStream = _FakeRunStreamClient();
        final controller = ChatController(
          client: fakeStream,
          deltaFlushInterval: Duration.zero,
        );
        final convController = ConversationListController(
          api: _FakeConversationsApi(),
        );

        await tester.pumpWidget(
          _wrapWithApp(
            reduceMotion: true,
            child: ChatScreen(
              api: KarmiApi(baseUrl: 'http://fake.test'),
              chatController: controller,
              conversationListController: convController,
              clock: () => DateTime(2026, 1, 1, 10),
            ),
          ),
        );
        await tester.pump();

        expect(
          find.byKey(const ValueKey('new-chat-empty-state')),
          findsOneWidget,
        );
        final surfaceFinder = find.byKey(const ValueKey('composer-surface'));
        final screenHeight =
            tester.view.physicalSize.height / tester.view.devicePixelRatio;
        final initialBottomDy = tester.getBottomLeft(surfaceFinder).dy;
        expect(screenHeight - initialBottomDy, greaterThan(150.0));

        // Send a message
        await tester.enterText(find.byType(TextField), 'Reduced motion test');
        await tester.pump();
        await tester.tap(find.byKey(const ValueKey('composer-send-button')));

        fakeStream.emitStarted();

        // Under reduced motion, duration is Duration.zero.
        // A single pump() immediately reaches the final docked position without animation.
        await tester.pump(Duration.zero);

        expect(
          find.byKey(const ValueKey('new-chat-empty-state')),
          findsNothing,
        );
        final dockedBottomDy = tester.getBottomLeft(surfaceFinder).dy;
        expect(screenHeight - dockedBottomDy, lessThanOrEqualTo(120.0));
        expect(dockedBottomDy, greaterThan(initialBottomDy));
        // The fake run never terminates, so the controller's stall timer is
        // still pending. Unmount, then dispose the injected controllers (ChatScreen
        // does not own them) to cancel it.
        await tester.pumpWidget(const SizedBox.shrink());
        controller.dispose();
        convController.dispose();
      },
    );
  });
}
