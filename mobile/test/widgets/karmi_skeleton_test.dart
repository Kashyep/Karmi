import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/features/history/conversation_list.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/widgets/karmi_skeleton.dart';

import '../support/fake_backend.dart';

Widget _wrap(Widget child, {bool reduceMotion = false}) {
  return MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: KarmiAccessibility(
        reduceTransparency: false,
        reduceMotion: reduceMotion,
        child: Scaffold(body: Center(child: child)),
      ),
    ),
  );
}

class _SlowFakeConversationsApi implements ConversationsApi {
  final Completer<ConversationPage> listCompleter =
      Completer<ConversationPage>();
  final Completer<MessagePage> messagesCompleter = Completer<MessagePage>();
  final Completer<List<ConversationSearchResult>> searchCompleter =
      Completer<List<ConversationSearchResult>>();

  @override
  String baseUrl = 'http://karmi.test';

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
  }) => listCompleter.future;

  @override
  Future<List<ConversationSearchResult>> search(
    String q, {
    int limit = 20,
  }) => searchCompleter.future;

  @override
  Future<ConversationView> get(String id) async {
    throw UnimplementedError();
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) => messagesCompleter.future;

  @override
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async {
    throw UnimplementedError();
  }

  @override
  Future<void> delete(String id) async {
    throw UnimplementedError();
  }

  @override
  Future<ConversationView> restore(String id) async {
    throw UnimplementedError();
  }
}

void main() {
  group('KarmiSkeleton', () {
    testWidgets('renders skeleton block with specified size and radius', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const KarmiSkeleton(
            width: 120,
            height: 24,
            borderRadius: BorderRadius.all(Radius.circular(8)),
          ),
        ),
      );

      expect(find.byType(KarmiSkeleton), findsOneWidget);
      expect(tester.hasRunningAnimations, isTrue);
    });

    testWidgets(
      'reduce motion renders static without transient callbacks or running animations',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            const KarmiSkeleton(width: 100, height: 20),
            reduceMotion: true,
          ),
        );
        await tester.pump();

        expect(find.byType(KarmiSkeleton), findsOneWidget);
        expect(tester.hasRunningAnimations, isFalse);
        expect(tester.binding.transientCallbackCount, 0);

        await tester.pump(const Duration(milliseconds: 500));
        expect(tester.hasRunningAnimations, isFalse);
        expect(tester.binding.transientCallbackCount, 0);
      },
    );

    testWidgets('controller is disposed on unmount with no ticker error', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const KarmiSkeleton(width: 80, height: 16)),
      );
      await tester.pump();
      expect(tester.hasRunningAnimations, isTrue);

      await tester.pumpWidget(_wrap(const SizedBox.shrink()));
      await tester.pump();

      expect(find.byType(KarmiSkeleton), findsNothing);
      expect(tester.hasRunningAnimations, isFalse);
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets(
      'KarmiHistorySkeletonList is shown when history list is loading',
      (tester) async {
        final api = _SlowFakeConversationsApi();
        final controller = ConversationListController(api: api);
        addTearDown(controller.dispose);

        final refreshFuture = controller.refresh();

        await tester.pumpWidget(
          _wrap(
            ConversationList(
              controller: controller,
              onOpen: (_) {},
              onNewChat: () {},
            ),
          ),
        );
        await tester.pump();

        expect(find.byType(KarmiHistorySkeletonList), findsOneWidget);
        expect(find.byType(KarmiHistorySkeletonRow), findsWidgets);
        expect(find.byType(CircularProgressIndicator), findsNothing);

        api.listCompleter.complete(
          const ConversationPage(items: [], nextCursor: null),
        );
        await refreshFuture;
        await tester.pump();
      },
    );
    testWidgets(
      'KarmiHistorySkeletonList is shown when search is in flight and results empty',
      (tester) async {
        final api = _SlowFakeConversationsApi();
        final controller = ConversationListController(
          api: api,
          searchDebounce: Duration.zero,
        );
        addTearDown(controller.dispose);

        final refreshFuture = controller.refresh();
        await tester.pumpWidget(
          _wrap(
            ConversationList(
              controller: controller,
              onOpen: (_) {},
              onNewChat: () {},
            ),
          ),
        );
        await tester.pump();
        api.listCompleter.complete(
          const ConversationPage(items: [], nextCursor: null),
        );
        await refreshFuture;
        await tester.pump();

        controller.onQueryChanged('test query');
        await tester.pump(const Duration(milliseconds: 10));

        expect(find.byType(KarmiHistorySkeletonList), findsOneWidget);
        expect(find.byType(CircularProgressIndicator), findsNothing);

        api.searchCompleter.complete(const []);
        await tester.pump();
      },
    );


    testWidgets(
      'KarmiMessageHistorySkeleton is shown when message history is loading in ChatScreen',
      (tester) async {
        final backend = FakeBackend.healthy();
        final convApi = _SlowFakeConversationsApi();

        await tester.pumpWidget(
          _wrap(
            ChatScreen(
              api: backend.api(),
              conversationId: 'conv-test-1',
              conversationsApi: convApi,
            ),
          ),
        );
        await tester.pump();

        // While convApi.messages() is pending, KarmiMessageHistorySkeleton is shown
        expect(find.byType(KarmiMessageHistorySkeleton), findsOneWidget);
        expect(find.byType(KarmiSkeleton), findsWidgets);
        expect(find.byType(LinearProgressIndicator), findsNothing);

        convApi.messagesCompleter.complete(const MessagePage(items: []));
        await tester.pump();
      },
    );
  });
}
