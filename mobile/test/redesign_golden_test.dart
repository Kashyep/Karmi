@Tags(['golden'])
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;

import 'support/fake_backend.dart';
import 'support/harness.dart';

/// Supported redesign visual matrix: light/dark × glass/opaque at scale 1.0.
final redesignEnvs = [
  for (final b in Brightness.values)
    for (final rt in [false, true])
      Env(brightness: b, textScale: 1.0, reduceTransparency: rt),
];

Future<void> send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField).last, text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send message'));
  await tester.pump();
}

http.Response sseResponse(
  String text, {
  String runId = 'run-1',
  String conversationId = 'conv-1',
  String finishReason = 'stop',
  String outcome = 'ACCEPT',
}) {
  final deltaJson = jsonEncode({'text': text});
  final finishedJson = jsonEncode({
    'finish_reason': finishReason,
    'outcome': outcome,
  });
  final sse =
      'event: run.started\n'
      'data: {"run_id":"$runId","conversation_id":"$conversationId","user_message_id":"msg-u","assistant_message_id":"msg-a","seq":0}\n\n'
      'id: 1\n'
      'event: message.delta\n'
      'data: $deltaJson\n\n'
      'event: run.finished\n'
      'data: $finishedJson\n\n';
  return http.Response(
    sse,
    200,
    headers: {'content-type': 'text/event-stream'},
  );
}

List<Map<String, dynamic>> createTestConversations() {
  final now = FakeBackend.pinnedNow;
  final todayDate = DateTime(now.year, now.month, now.day, 12);
  final yesterdayDate = todayDate.subtract(const Duration(days: 1));
  final prev7Date = todayDate.subtract(const Duration(days: 3));
  final olderDate = todayDate.subtract(const Duration(days: 30));

  return [
    {
      'id': 'conv-pinned',
      'title': 'Quarterly Planning',
      'pinned': true,
      'updated_at': todayDate.toIso8601String(),
      'message_count': 5,
    },
    {
      'id': 'conv-1',
      'title': 'Daily sync and goals',
      'pinned': false,
      'updated_at': todayDate.toIso8601String(),
      'message_count': 3,
    },
    {
      'id': 'conv-yesterday',
      'title': 'Design review feedback',
      'pinned': false,
      'updated_at': yesterdayDate.toIso8601String(),
      'message_count': 2,
    },
    {
      'id': 'conv-prev7',
      'title': 'API schema migration',
      'pinned': false,
      'updated_at': prev7Date.toIso8601String(),
      'message_count': 8,
    },
    {
      'id': 'conv-older',
      'title': 'Initial project kickoff',
      'pinned': false,
      'updated_at': olderDate.toIso8601String(),
      'message_count': 14,
    },
  ];
}

void main() {
  Future<void> fontsReady(WidgetTester tester) async {
    await tester.runAsync(GoogleFonts.pendingFonts);
    await settle(tester);
  }

  for (final env in redesignEnvs) {
    group(env.name, () {
      testWidgets('chat_rich', (tester) async {
        const richMarkdown = '''
Here is the schedule:

| Day | Task |
| --- | --- |
| Mon | Design review |
| Wed | Implementation |
| Fri | Ship release |

```dart
void main() {
  print('Hello Karmi');
}
```
''';

        final backend = FakeBackend.healthy()
          ..on(
            'POST',
            '/v1/chat/stream',
            (_) => sseResponse(richMarkdown, outcome: 'ASK_USER'),
          );

        await pumpApp(tester, backend: backend, env: env);
        await send(tester, 'Show me the schedule');
        await fontsReady(tester);
        expectNoOverflow(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('chat_rich_${env.name}')),
        );
      });

      testWidgets('history_drawer', (tester) async {
        final backend = FakeBackend.healthy()
          ..on(
            'GET',
            '/v1/conversations',
            (_) => jsonResponse({
              'items': createTestConversations(),
              'next_cursor': null,
            }),
          )
          ..on(
            'GET',
            '/v1/conversations/conv-1/messages',
            (_) => jsonResponse({'items': [], 'has_more_before': false}),
          );

        await pumpApp(tester, backend: backend, env: env);
        await send(tester, 'Hello');
        await fontsReady(tester);
        await tester.tap(find.byTooltip('Conversation history'));
        await fontsReady(tester);
        expectNoOverflow(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('history_drawer_${env.name}')),
        );
      });

      testWidgets('history_rail', (tester) async {
        final backend = FakeBackend.healthy()
          ..on(
            'GET',
            '/v1/conversations',
            (_) => jsonResponse({
              'items': createTestConversations(),
              'next_cursor': null,
            }),
          )
          ..on(
            'GET',
            '/v1/conversations/conv-1/messages',
            (_) => jsonResponse({'items': [], 'has_more_before': false}),
          );

        await pumpApp(
          tester,
          backend: backend,
          env: env,
          size: const Size(1280, 800),
        );
        await send(tester, 'Hello');
        await fontsReady(tester);
        expectNoOverflow(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('history_rail_${env.name}')),
        );
      });

      testWidgets('streaming_processing', (tester) async {
        final completer = Completer<http.Response>();
        addTearDown(() {
          if (!completer.isCompleted) {
            completer.complete(sseResponse('teardown'));
          }
        });

        final backend = FakeBackend.healthy()
          ..on('POST', '/v1/chat/stream', (_) => completer.future);

        await pumpApp(tester, backend: backend, env: env);
        await send(tester, 'Plan my week');
        await fontsReady(tester);
        expectNoOverflow(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('streaming_processing_${env.name}')),
        );
        completer.complete(sseResponse('done'));
        await settle(tester);
      });

      testWidgets('chat_error', (tester) async {
        final backend = FakeBackend.healthy()
          ..on('POST', '/v1/chat/stream', FakeBackend.network());

        await pumpApp(tester, backend: backend, env: env);
        await send(tester, 'hello');
        await settle(tester);
        await fontsReady(tester);
        expectNoOverflow(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('chat_error_${env.name}')),
        );
      });
    });
  }
}
