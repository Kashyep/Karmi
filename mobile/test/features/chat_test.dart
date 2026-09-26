import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/features/chat/message_bubble.dart';
import 'package:karmi_app/features/chat/status_chip.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/features/tasks/task_confirmation_sheet.dart';
import 'package:karmi_app/widgets/feedback.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

Future<void> send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send message'));
  await tester.pump();
}

FakeBackend backendWith(Handler messages) =>
    FakeBackend.healthy()..on('POST', '/v1/messages', messages);

void main() {
  testWidgets('empty: Trykker empty state, send disabled until text', (
    tester,
  ) async {
    await pumpApp(tester);
    final quote = find.text(
      'Ask for a draft, a task, or something to remember.',
    );
    expect(quote, findsOneWidget);
    expect(tester.widget<Text>(quote).style?.fontFamily, 'Trykker_regular');
    expect(find.byType(EmptyState), findsOneWidget);
    final send = tester.widget<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.send),
        matching: find.byType(IconButton),
      ),
    );
    expect(send.onPressed, isNull);
    expect(find.byType(KarmiLoader), findsNothing);
    await expectA11yGuidelines(tester);
  });

  testWidgets('pending: loader only while the request is in flight', (
    tester,
  ) async {
    final reply = Completer<http.Response>();
    await pumpApp(tester, backend: backendWith((_) => reply.future));
    await send(tester, 'Plan my week');
    expect(find.text('Working on your message'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    // Composer send is disabled while pending.
    await tester.enterText(find.byType(TextField), 'second');
    await tester.pump();
    final button = tester.widget<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.send),
        matching: find.byType(IconButton),
      ),
    );
    expect(button.onPressed, isNull);

    reply.complete(jsonResponse(messageJson('ACCEPT')));
    await settle(tester);
    expect(find.byType(KarmiLoader), findsNothing);
    expect(find.text('Completed'), findsOneWidget);
  });

  testWidgets('pending under reduced motion: static icon plus text', (
    tester,
  ) async {
    final reply = Completer<http.Response>();
    await pumpApp(
      tester,
      backend: backendWith((_) => reply.future),
      env: const Env(reduceMotion: true),
    );
    await send(tester, 'Plan my week');
    expect(find.text('Working on your message'), findsOneWidget);
    expect(find.byKey(const ValueKey('karmi-loader-static')), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    reply.complete(jsonResponse(messageJson('ACCEPT')));
    await settle(tester);
  });

  const outcomeCopy = {
    'ACCEPT': 'Completed',
    'REPAIR': 'Corrected',
    'ESCALATE': 'Needs review',
    'ASK_USER': 'Awaiting confirmation',
    'SAFE_STOP': 'Could not confirm completion',
    'DEFERRED': 'Deferred',
    'BRAND_NEW_OUTCOME': 'Status unknown',
  };
  for (final MapEntry(key: wire, value: copy) in outcomeCopy.entries) {
    testWidgets('outcome $wire shows "$copy" with an icon', (tester) async {
      await pumpApp(
        tester,
        backend: backendWith(
          (_) => jsonResponse(messageJson(wire, response: 'Reply for $wire')),
        ),
      );
      await send(tester, 'hello');
      await settle(tester);
      expect(find.text('Reply for $wire'), findsOneWidget);
      final chip = find.ancestor(
        of: find.text(copy),
        matching: find.byType(StatusChip),
      );
      expect(chip, findsOneWidget);
      expect(
        find.descendant(of: chip, matching: find.byType(Icon)),
        findsOneWidget,
      );
      await expectA11yGuidelines(tester);
    });
  }

  testWidgets('new replies are live regions for screen readers', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    await send(tester, 'first');
    await settle(tester);
    await send(tester, 'second');
    await settle(tester);
    final replies = tester
        .widgetList<MessageBubble>(find.byType(MessageBubble))
        .where((b) => b.reply != null)
        .toList();
    expect(replies, hasLength(2));
    expect(replies.first.announce, isFalse);
    expect(replies.last.announce, isTrue);
    final replyNodes = find.bySemanticsLabel(RegExp('^Karmi replied'));
    expect(replyNodes, findsNWidgets(2));
    bool live(Finder f) =>
        tester.getSemantics(f).getSemanticsData().flagsCollection.isLiveRegion;
    expect(live(replyNodes.first), isFalse);
    expect(live(replyNodes.last), isTrue);
    handle.dispose();
  });

  testWidgets('failed (500): ErrorBanner, no raw exception text', (
    tester,
  ) async {
    await pumpApp(
      tester,
      backend: backendWith((_) => http.Response('Traceback: boom', 500)),
    );
    await send(tester, 'hello');
    await settle(tester);
    expect(find.byType(ErrorBanner), findsOneWidget);
    expect(find.text('Could not complete'), findsWidgets);
    expect(find.textContaining('Exception'), findsNothing);
    expect(find.textContaining('500'), findsNothing);
    expect(find.textContaining('Traceback'), findsNothing);
    await expectA11yGuidelines(tester);
  });

  testWidgets('offline: banner and retry reuses the idempotency key', (
    tester,
  ) async {
    var calls = 0;
    final app = await pumpApp(
      tester,
      backend: backendWith((request) {
        calls++;
        if (calls == 1) return FakeBackend.network()(request);
        return jsonResponse(messageJson('ACCEPT'));
      }),
    );
    await send(tester, 'hello');
    await settle(tester);
    expect(find.text("You're offline"), findsOneWidget);
    expect(find.text('Not sent: offline'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await settle(tester);
    expect(find.text("You're offline"), findsNothing);
    expect(find.text('Completed'), findsOneWidget);

    final keys = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .map((r) => (jsonDecode(r.body) as Map)['idempotency_key'])
        .toList();
    expect(keys, hasLength(2));
    expect(keys.first, keys.last);
  });

  testWidgets('409 in flight: explains and re-checks with the same key', (
    tester,
  ) async {
    var calls = 0;
    final app = await pumpApp(
      tester,
      backend: backendWith((_) {
        calls++;
        return calls == 1
            ? jsonResponse({
                'detail':
                    'request already in flight; retry to observe its result',
              }, 409)
            : jsonResponse(messageJson('ACCEPT'));
      }),
    );
    await send(tester, 'hello');
    await settle(tester);
    expect(find.text('Still working on this message'), findsOneWidget);
    await expectA11yGuidelines(tester);
    await tester.tap(find.text('Check again'));
    await settle(tester);
    expect(find.text('Completed'), findsOneWidget);
    final keys = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .map((r) => (jsonDecode(r.body) as Map)['idempotency_key'])
        .toSet();
    expect(keys, hasLength(1));
  });

  testWidgets('limit reached (429): allowance banner opens plans', (
    tester,
  ) async {
    await pumpApp(
      tester,
      backend: backendWith(
        (_) => jsonResponse({
          'detail': {
            'code': 'ALLOWANCE_EXHAUSTED',
            'message': 'everyday allowance exhausted',
            'reset_at': '2026-09-27T00:00:00+00:00',
          },
        }, 429),
      ),
    );
    await send(tester, 'hello');
    await settle(tester);
    expect(find.text('Allowance reached'), findsWidgets);
    expect(find.textContaining('resets at'), findsOneWidget);
    await expectA11yGuidelines(tester);
    await tester.tap(find.text('View plans'));
    await settle(tester);
    expect(find.byType(PlanSelectionScreen), findsOneWidget);
  });

  testWidgets('401 ends the session and returns to Welcome', (tester) async {
    final app = await pumpApp(
      tester,
      backend: backendWith(
        (_) => jsonResponse({'detail': 'invalid session'}, 401),
      ),
    );
    await send(tester, 'hello');
    await settle(tester);
    expect(app.session.isSignedIn, isFalse);
    expect(find.text('Session ended'), findsOneWidget);
  });

  testWidgets('ASK_USER opens the opaque confirmation sheet', (tester) async {
    await pumpApp(
      tester,
      backend: backendWith(
        (_) => jsonResponse(
          messageJson('ASK_USER', response: 'Which day should I remind you?'),
        ),
      ),
    );
    await send(tester, 'remind me');
    await settle(tester);
    await tester.tap(find.text('Review details'));
    await settle(tester);
    expect(find.byType(TaskConfirmationSheet), findsOneWidget);
    expect(find.text('Confirm task'), findsOneWidget);
    expect(find.text('Not provided'), findsNWidgets(4));
    final confirm = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Confirm'),
    );
    expect(confirm.onPressed, isNull);
    final body = tester.widget<ColoredBox>(
      find
          .descendant(
            of: find.byType(TaskConfirmationSheet),
            matching: find.byType(ColoredBox),
          )
          .first,
    );
    expect(body.color.a, 1.0);
    await expectA11yGuidelines(tester);
  });

  for (final rt in [false, true]) {
    testWidgets(
      'text scale 2.0 does not overflow (${rt ? 'opaque' : 'glass'})',
      (tester) async {
        var calls = 0;
        await pumpApp(
          tester,
          env: Env(textScale: 2.0, reduceTransparency: rt),
          backend: backendWith((request) {
            calls++;
            if (calls == 2) return FakeBackend.network()(request);
            return jsonResponse(
              messageJson(
                'SAFE_STOP',
                response:
                    'I could not confirm whether the reminder was saved. '
                    "I'm checking its status.",
              ),
            );
          }),
        );
        expectNoOverflow(tester);
        await send(tester, 'Remind me to call the bank tomorrow at 9');
        await settle(tester);
        await send(tester, 'And again');
        await settle(tester);
        expectNoOverflow(tester);
        expect(find.text("You're offline"), findsOneWidget);
        await expectA11yGuidelines(tester);
      },
    );
  }
}
