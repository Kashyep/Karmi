import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/chat/chat_entry.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';
import 'package:karmi_app/features/chat/rendering/code_block.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

void main() {
  group('MessageBubble layout & interactions', () {
    testWidgets(
      '1. ASK_USER renders confirmation chip, Review details button, and fires onReviewDetails',
      (tester) async {
        tester.view.physicalSize = const Size(600, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        var reviewedCount = 0;
        final chatMessage = ChatMessageView(
          id: 'msg-ask-user',
          conversationId: 'c1',
          role: 'assistant',
          status: MessageStatus.complete,
          content: 'Please confirm deletion of this resource.',
          outcome: Outcome.askUser,
          createdAt: DateTime(2026, 1, 1),
          updatedAt: DateTime(2026, 1, 1),
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(
              body: MessageBubble.chatMessage(
                chatMessage: chatMessage,
                onReviewDetails: () => reviewedCount++,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Awaiting confirmation'), findsOneWidget);
        expect(find.text('Review details'), findsOneWidget);

        await tester.tap(find.text('Review details'));
        await tester.pumpAndSettle();

        expect(reviewedCount, 1);
      },
    );

    testWidgets(
      '2. Assistant reply renders text, Karmi header, and readable column constraint without card decoration',
      (tester) async {
        tester.view.physicalSize = const Size(1000, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        const replyText = 'Here is the response from Karmi assistant.';
        const messageView = MessageView(
          runId: 'r1',
          status: 'COMPLETED',
          outcome: Outcome.accept,
          response: replyText,
        );
        final replyEntry = ReplyEntry(id: 'rep-1', message: messageView);

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(body: MessageBubble.reply(reply: replyEntry)),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text(replyText), findsOneWidget);
        expect(find.text('Karmi'), findsOneWidget);

        // Verify no Material Card
        expect(find.byType(Card), findsNothing);

        // Verify text is inside Center and ConstrainedBox with maxWidth <= KarmiShape.readableColumnMaxWidth
        final centerFinder = find.ancestor(
          of: find.text(replyText),
          matching: find.byType(Center),
        );
        expect(centerFinder, findsWidgets);

        final constrainedBox = tester.widget<ConstrainedBox>(
          find
              .descendant(
                of: centerFinder,
                matching: find.byType(ConstrainedBox),
              )
              .first,
        );
        expect(
          constrainedBox.constraints.maxWidth,
          lessThanOrEqualTo(KarmiShape.readableColumnMaxWidth),
        );

        // Verify no decorated Container with a border wrapping the reply text
        final borderContainer = find.ancestor(
          of: find.text(replyText),
          matching: find.byWidgetPredicate(
            (w) =>
                w is Container &&
                w.decoration is BoxDecoration &&
                (w.decoration as BoxDecoration).border != null,
          ),
        );
        expect(borderContainer, findsNothing);
      },
    );

    testWidgets(
      '3. User message bubble width is <= 75% in 600px viewport and right-aligned',
      (tester) async {
        tester.view.physicalSize = const Size(600, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        const userText =
            'This is a sufficiently long user message intended to verify that '
            'the width of the bubble does not exceed seventy five percent of '
            'the viewport constraint, and aligns to the right side.';
        final userEntry = UserEntry(
          id: 'u1',
          text: userText,
          idempotencyKey: 'k1',
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(body: MessageBubble.user(entry: userEntry)),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text(userText), findsOneWidget);

        final pillFinder = find.byWidgetPredicate(
          (w) =>
              w is Container &&
              w.decoration is BoxDecoration &&
              (w.decoration as BoxDecoration).borderRadius ==
                  KarmiShape.userPillRadius,
        );
        expect(pillFinder, findsOneWidget);

        final pillRect = tester.getRect(pillFinder);
        expect(pillRect.width, lessThanOrEqualTo(600 * 0.75));
        expect(pillRect.right, equals(600.0));
      },
    );

    testWidgets(
      '4. Action toolbar on completed reply has accessible tap targets and fires callbacks',
      (tester) async {
        tester.view.physicalSize = const Size(800, 600);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        FeedbackRating? receivedFeedback;
        var regenerated = false;

        const replyText = 'Completed reply awaiting toolbar interactions.';
        const messageView = MessageView(
          runId: 'r2',
          status: 'COMPLETED',
          outcome: Outcome.accept,
          response: replyText,
        );
        final replyEntry = ReplyEntry(id: 'rep-2', message: messageView);

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(
              body: MessageBubble.reply(
                reply: replyEntry,
                onFeedback: (rating) => receivedFeedback = rating,
                onRegenerate: () => regenerated = true,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final copyButton = find.byTooltip('Copy');
        final regenerateButton = find.byTooltip('Regenerate response');
        final thumbsUpButton = find.byTooltip('Thumbs up');
        final thumbsDownButton = find.byTooltip('Thumbs down');

        expect(copyButton, findsOneWidget);
        expect(regenerateButton, findsOneWidget);
        expect(thumbsUpButton, findsOneWidget);
        expect(thumbsDownButton, findsOneWidget);

        // Verify each tap target is >= 44x44
        for (final btn in [
          copyButton,
          regenerateButton,
          thumbsUpButton,
          thumbsDownButton,
        ]) {
          final size = tester.getSize(btn);
          expect(size.width, greaterThanOrEqualTo(44.0));
          expect(size.height, greaterThanOrEqualTo(44.0));
        }

        // Tap thumbs up and verify onFeedback fired with positive FeedbackRating
        await tester.tap(thumbsUpButton);
        await tester.pumpAndSettle();
        expect(receivedFeedback, FeedbackRating.up);

        // Tap regenerate and verify onRegenerate fired
        await tester.tap(regenerateButton);
        await tester.pumpAndSettle();
        expect(regenerated, isTrue);

        // Tap copy and verify copy behavior
        await tester.tap(copyButton);
        await tester.pumpAndSettle();
        expect(find.text('Copied'), findsWidgets);
      },
    );

    testWidgets(
      '5. Code block header renders language label and Copy/Wrap tooltips',
      (tester) async {
        tester.view.physicalSize = const Size(800, 600);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        const code = 'void main() {\n  print("Hello, Karmi!");\n}';
        const language = 'dart';

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: const Scaffold(
              body: CodeBlock(code: code, language: language),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text(language), findsOneWidget);
        expect(find.byTooltip('Copy code'), findsOneWidget);
        expect(find.byTooltip('Wrap long lines'), findsOneWidget);
      },
    );

    testWidgets(
      '6. Assistant reply liveRegion is false during streaming and true when finished',
      (tester) async {
        final handle = tester.ensureSemantics();

        final streamingMessage = ChatMessageView(
          id: 'msg-stream-1',
          conversationId: 'c1',
          role: 'assistant',
          status: MessageStatus.streaming,
          content: 'Streaming reply in progress...',
          createdAt: DateTime(2026, 1, 1),
          updatedAt: DateTime(2026, 1, 1),
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(
              body: MessageBubble.chatMessage(
                chatMessage: streamingMessage,
                announce: true,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final streamingNode = tester.getSemantics(
          find.bySemanticsLabel(RegExp('^Karmi replied')),
        );
        // ignore: deprecated_member_use
        expect(streamingNode.hasFlag(SemanticsFlag.isLiveRegion), isFalse);
        expect(
          streamingNode.getSemanticsData().flagsCollection.isLiveRegion,
          isFalse,
        );

        final finishedMessage = streamingMessage.copyWith(
          status: MessageStatus.complete,
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(
              body: MessageBubble.chatMessage(
                chatMessage: finishedMessage,
                announce: true,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final finishedNode = tester.getSemantics(
          find.bySemanticsLabel(RegExp('^Karmi replied')),
        );
        // ignore: deprecated_member_use
        expect(finishedNode.hasFlag(SemanticsFlag.isLiveRegion), isTrue);
        expect(
          finishedNode.getSemanticsData().flagsCollection.isLiveRegion,
          isTrue,
        );
        handle.dispose();
      },
    );
  });
}
