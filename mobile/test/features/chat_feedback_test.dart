import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/features/chat/error_card.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

Future<void> send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send message'));
  await settle(tester);
}

http.Response sseResponse(
  String text, {
  String runId = 'run-1',
  String userMessageId = 'msg-u',
  String assistantMessageId = 'msg-a',
  String finishReason = 'stop',
  String outcome = 'success',
}) {
  final sse = 'event: run.started\n'
      'data: {"run_id":"$runId","conversation_id":"conv-1","user_message_id":"$userMessageId","assistant_message_id":"$assistantMessageId","seq":0}\n\n'
      'id: 1\n'
      'event: message.delta\n'
      'data: {"text":"$text"}\n\n'
      'event: run.finished\n'
      'data: {"finish_reason":"$finishReason","outcome":"$outcome"}\n\n';
  return http.Response(
    sse,
    200,
    headers: {'content-type': 'text/event-stream'},
  );
}
void main() {
  testWidgets(
    'assistant reply displays accessible thumbs and regenerate actions',
    (tester) async {
      final backend = FakeBackend.healthy()
        ..on(
          'POST',
          '/v1/chat/stream',
          (_) => sseResponse('Here is your drafted email.'),
        );

      await pumpApp(tester, backend: backend);
      await send(tester, 'Draft email');

      expect(find.text('Here is your drafted email.'), findsOneWidget);

      // Verify actions exist with accessible tooltips and tap targets
      final thumbsUpFinder = find.byWidgetPredicate(
        (w) => w is IconButton && w.tooltip == 'Thumbs up',
      );
      final thumbsDownFinder = find.byWidgetPredicate(
        (w) => w is IconButton && w.tooltip == 'Thumbs down',
      );
      final regenFinder = find.byWidgetPredicate(
        (w) => w is IconButton && w.tooltip == 'Regenerate response',
      );

      expect(thumbsUpFinder, findsOneWidget);
      expect(thumbsDownFinder, findsOneWidget);
      expect(regenFinder, findsOneWidget);

      final upButton = tester.widget<IconButton>(thumbsUpFinder);
      expect(upButton.constraints?.minWidth, greaterThanOrEqualTo(48.0));
      expect(upButton.constraints?.minHeight, greaterThanOrEqualTo(48.0));

      final downButton = tester.widget<IconButton>(thumbsDownFinder);
      expect(downButton.constraints?.minWidth, greaterThanOrEqualTo(48.0));
      expect(downButton.constraints?.minHeight, greaterThanOrEqualTo(48.0));

      final regenButton = tester.widget<IconButton>(regenFinder);
      expect(regenButton.constraints?.minWidth, greaterThanOrEqualTo(48.0));
      expect(regenButton.constraints?.minHeight, greaterThanOrEqualTo(48.0));
    },
  );

  testWidgets('thumbs up sends feedback and selects the rating', (
    tester,
  ) async {
    final backend = FakeBackend.healthy()
      ..on(
        'POST',
        '/v1/chat/stream',
        (_) => sseResponse('Plan ready.', runId: 'run-1'),
      );

    await pumpApp(tester, backend: backend);
    await send(tester, 'Plan week');

    await tester.tap(find.byTooltip('Thumbs up'));
    await settle(tester);

    // Backend received feedback
    final feedbackReq = backend.requests.firstWhere(
      (r) => r.url.path == '/v1/runs/run-1/feedback',
    );
    expect(jsonDecode(feedbackReq.body), {'rating': 'up'});
    // Thumbs up is selected
    final upBtn = tester.widget<IconButton>(
      find.byWidgetPredicate(
        (w) => w is IconButton && w.tooltip == 'Thumbs up',
      ),
    );
    expect(upBtn.isSelected, isTrue);
  });

  testWidgets('thumbs down shows reason picker and sends reason', (
    tester,
  ) async {
    final backend = FakeBackend.healthy()
      ..on(
        'POST',
        '/v1/chat/stream',
        (_) => sseResponse('Summary of file.', runId: 'run-1'),
      );
    await pumpApp(tester, backend: backend);
    await send(tester, 'Summarize');

    await tester.tap(find.byTooltip('Thumbs down'));
    await settle(tester);

    // Initial down rating sent
    expect(
      backend.requests.any(
        (r) =>
            r.url.path == '/v1/runs/run-1/feedback' &&
            jsonDecode(r.body)['rating'] == 'down',
      ),
      isTrue,
    );

    // Reason chips appear
    expect(find.text('Wrong'), findsOneWidget);
    expect(find.text('Unclear'), findsOneWidget);
    expect(find.text('Too slow'), findsOneWidget);
    expect(find.text('Other'), findsOneWidget);

    // Select reason 'Wrong'
    await tester.tap(find.text('Wrong'));
    await settle(tester);

    // Backend received feedback with reason
    final withReasonReq = backend.requests.lastWhere(
      (r) => r.url.path == '/v1/runs/run-1/feedback',
    );
    expect(jsonDecode(withReasonReq.body), {
      'rating': 'down',
      'reason': 'wrong',
    });

    final wrongChip = tester.widget<ChoiceChip>(
      find.widgetWithText(ChoiceChip, 'Wrong'),
    );
    expect(wrongChip.selected, isTrue);
  });

  testWidgets('regenerate action calls API and replaces reply in transcript', (
    tester,
  ) async {
    final backend = FakeBackend.healthy()
      ..on(
        'POST',
        '/v1/chat/stream',
        (_) => sseResponse('First version', runId: 'run-1', assistantMessageId: 'msg-a'),
      )
      ..on(
        'POST',
        '/v1/messages/msg-a/regenerate',
        (_) => sseResponse('Second improved version', runId: 'run-2', assistantMessageId: 'msg-a-2'),
      );

    await pumpApp(tester, backend: backend);
    await send(tester, 'Draft note');

    expect(find.text('First version'), findsOneWidget);

    // Tap regenerate
    await tester.tap(find.byTooltip('Regenerate response'));
    await settle(tester);

    // Second improved version is rendered in transcript
    expect(find.text('Second improved version'), findsOneWidget);

    final regenReq = backend.requests.firstWhere(
      (r) => r.url.path == '/v1/messages/msg-a/regenerate',
    );
    expect(regenReq.method, 'POST');
  });

  testWidgets('error in feedback displays ErrorBanner with retry', (
    tester,
  ) async {
    var failFeedback = true;
    final backend = FakeBackend.healthy()
      ..on(
        'POST',
        '/v1/chat/stream',
        (_) => sseResponse('Reply', runId: 'run-1'),
      )
      ..on('POST', '/v1/runs/run-1/feedback', (_) {
        if (failFeedback) {
          return jsonResponse({'detail': 'failed'}, 500);
        }
        return jsonResponse({'run_id': 'run-1', 'rating': 'up'});
      });

    await pumpApp(tester, backend: backend);
    await send(tester, 'Hello');

    await tester.tap(find.byTooltip('Thumbs up'));
    await settle(tester);

    // ErrorCard displayed
    expect(find.byType(ErrorCard), findsOneWidget);

    // Tap retry on ErrorCard
    failFeedback = false;
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(find.byType(ErrorCard), findsNothing);
  });
}
