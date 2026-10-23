import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/debug_meta.dart';
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/chat/chat_entry.dart';
import 'package:karmi_app/features/chat/debug_meta_line.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

const _meta = DebugMeta(
  servedModel: 'model-x',
  servedProvider: null,
  attemptCount: 1,
  fallbackUsed: false,
  latencyMs: 1234,
  inputTokens: 10,
  outputTokens: null,
  harnessVersion: '4.1.0',
);

void main() {
  group('showDebugMeta', () {
    test('is true only when env flag is on and debug is present', () {
      expect(showDebugMeta(envFlag: true, debug: _meta), isTrue);
      expect(showDebugMeta(envFlag: true, debug: null), isFalse);
      expect(showDebugMeta(envFlag: false, debug: _meta), isFalse);
      expect(showDebugMeta(envFlag: false, debug: null), isFalse);
    });
  });

  group('debugMetaSummary', () {
    test('joins present parts and omits null parts', () {
      expect(
        debugMetaSummary(_meta),
        'model-x · attempts 1 · 1234 ms · 10/? tokens · harness 4.1.0',
      );
    });

    test('includes fallback marker when used', () {
      final summary = debugMetaSummary(
        const DebugMeta(
          servedModel: null,
          servedProvider: null,
          attemptCount: 3,
          fallbackUsed: true,
          latencyMs: null,
          inputTokens: null,
          outputTokens: null,
          harnessVersion: '',
        ),
      );
      expect(summary, 'attempts 3 · fallback');
    });
  });

  testWidgets('DebugMetaLine renders the summary as one muted line', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
        home: Scaffold(body: DebugMetaLine(meta: _meta)),
      ),
    );
    expect(find.textContaining('harness 4.1.0'), findsOneWidget);
  });

  testWidgets(
    'reply with debug present renders no debug line when KARMI_DEBUG_META is unset',
    (tester) async {
      tester.view.physicalSize = const Size(1000, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      const messageView = MessageView(
        runId: 'r-debug',
        status: 'COMPLETED',
        outcome: Outcome.accept,
        response: 'Reply with debug metadata.',
        debug: _meta,
      );
      final replyEntry = ReplyEntry(id: 'rep-debug', message: messageView);

      await tester.pumpWidget(
        MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: Scaffold(body: MessageBubble.reply(reply: replyEntry)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Reply with debug metadata.'), findsOneWidget);
      expect(find.textContaining('harness'), findsNothing);
    },
  );
}
