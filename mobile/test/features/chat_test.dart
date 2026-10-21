import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/features/chat/chat_entry.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
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
      'Ask a study question, or get help with maths or code.',
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

  testWidgets('beta capacity full (429): banner says try again later', (
    tester,
  ) async {
    await pumpApp(
      tester,
      backend: backendWith(
        (_) => jsonResponse({
          'detail': {
            'code': 'BETA_CAPACITY_FULL',
            'message': "Karmi's beta has reached today's limit.",
            'reset_at': '2026-10-22T00:00:00+00:00',
          },
        }, 429),
      ),
    );
    await send(tester, 'hello');
    await settle(tester);
    expect(find.text('Karmi beta is full for today'), findsOneWidget);
    expect(find.text('Beta full today'), findsOneWidget);
    expect(find.textContaining('try again after'), findsOneWidget);
    expect(find.text('View plans'), findsNothing);
    await expectA11yGuidelines(tester);
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

  testWidgets('sendMessage posts history (and omits it when empty)', (
    tester,
  ) async {
    final app = await pumpApp(
      tester,
      backend: backendWith((request) {
        return jsonResponse(
          messageJson('ACCEPT', response: 'Reply to message'),
        );
      }),
    );

    // 1. First message: history is empty and omitted from JSON body.
    await send(tester, 'First message');
    await settle(tester);

    final req1 = app.backend.requests.firstWhere(
      (r) => r.url.path == '/v1/messages',
    );
    final body1 = jsonDecode(req1.body) as Map<String, dynamic>;
    expect(body1['text'], 'First message');
    expect(body1.containsKey('history'), isFalse);

    // 2. Second message: history contains the completed first turn.
    await send(tester, 'Second message');
    await settle(tester);

    final req2 = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .toList()[1];
    final body2 = jsonDecode(req2.body) as Map<String, dynamic>;
    expect(body2['text'], 'Second message');
    expect(body2['history'], [
      {'role': 'user', 'content': 'First message'},
      {'role': 'assistant', 'content': 'Reply to message'},
    ]);
  });

  testWidgets('retry reuses the stored history', (tester) async {
    var calls = 0;
    final app = await pumpApp(
      tester,
      backend: backendWith((request) {
        calls++;
        if (calls == 1) {
          return jsonResponse(messageJson('ACCEPT', response: 'First reply'));
        }
        if (calls == 2) {
          return FakeBackend.network()(request);
        }
        return jsonResponse(messageJson('ACCEPT', response: 'Second reply'));
      }),
    );

    await send(tester, 'First message');
    await settle(tester);

    // Second message fails offline.
    await send(tester, 'Second message');
    await settle(tester);
    expect(find.text("You're offline"), findsOneWidget);

    // Retry sending second message.
    await tester.tap(find.text('Retry'));
    await settle(tester);
    expect(find.text("You're offline"), findsNothing);

    final msgRequests = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .toList();
    expect(msgRequests.length, 3);

    final attempt1 = jsonDecode(msgRequests[1].body) as Map<String, dynamic>;
    final attempt2 = jsonDecode(msgRequests[2].body) as Map<String, dynamic>;

    expect(attempt1['idempotency_key'], attempt2['idempotency_key']);
    expect(attempt1['history'], isNotNull);
    expect(attempt1['history'], attempt2['history']);
    expect(attempt1['history'], [
      {'role': 'user', 'content': 'First message'},
      {'role': 'assistant', 'content': 'First reply'},
    ]);
  });

  testWidgets("'New chat' empties entries/history", (tester) async {
    final app = await pumpApp(
      tester,
      backend: backendWith((_) {
        return jsonResponse(messageJson('ACCEPT', response: 'Initial reply'));
      }),
    );

    await send(tester, 'Message before reset');
    await settle(tester);
    expect(find.text('Message before reset'), findsOneWidget);

    // Tap "New chat".
    await tester.tap(find.byTooltip('New chat'));
    await settle(tester);

    // Entries are emptied, empty state is displayed.
    expect(find.text('Message before reset'), findsNothing);
    expect(
      find.text('Ask a study question, or get help with maths or code.'),
      findsOneWidget,
    );

    // Send next message; context/history is dropped.
    await send(tester, 'Message in new chat');
    await settle(tester);

    final reqs = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .toList();
    expect(reqs.length, 2);
    final bodyAfterNewChat = jsonDecode(reqs[1].body) as Map<String, dynamic>;
    expect(bodyAfterNewChat['text'], 'Message in new chat');
    expect(bodyAfterNewChat.containsKey('history'), isFalse);
  });

  testWidgets('deferred/failed entries excluded from history', (tester) async {
    var calls = 0;
    final app = await pumpApp(
      tester,
      backend: backendWith((request) {
        calls++;
        if (calls == 1) {
          // Outcome DEFERRED.
          return jsonResponse(
            messageJson('DEFERRED', response: "couldn't reach the AI service"),
          );
        }
        if (calls == 2) {
          // Network failure.
          return FakeBackend.network()(request);
        }
        if (calls == 3) {
          // Successful response.
          return jsonResponse(messageJson('ACCEPT', response: 'Valid reply 3'));
        }
        return jsonResponse(messageJson('ACCEPT', response: 'Valid reply 4'));
      }),
    );

    // 1. DEFERRED reply
    await send(tester, 'Turn 1');
    await settle(tester);

    // 2. Failed reply
    await send(tester, 'Turn 2');
    await settle(tester);

    // 3. Turn 3: both Turn 1 (deferred) and Turn 2 (failed) should be excluded from history.
    await send(tester, 'Turn 3');
    await settle(tester);

    final reqs = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .toList();
    expect(reqs.length, 3);
    final body3 = jsonDecode(reqs[2].body) as Map<String, dynamic>;
    // History should be omitted because no valid completed turns exist before Turn 3.
    expect(body3.containsKey('history'), isFalse);

    // 4. Turn 4: Turn 3 was successful, so only Turn 3 should be in history.
    await send(tester, 'Turn 4');
    await settle(tester);

    final reqsAfter = app.backend.requests
        .where((r) => r.url.path == '/v1/messages')
        .toList();
    expect(reqsAfter.length, 4);
    final body4 = jsonDecode(reqsAfter[3].body) as Map<String, dynamic>;
    expect(body4['history'], [
      {'role': 'user', 'content': 'Turn 3'},
      {'role': 'assistant', 'content': 'Valid reply 3'},
    ]);
  });

  testWidgets(
    'tapping New chat while send is in flight leaves transcript empty and drops history',
    (tester) async {
      final completer = Completer<http.Response>();
      var callCount = 0;
      final app = await pumpApp(
        tester,
        backend: backendWith((request) {
          callCount++;
          if (callCount == 1) {
            return completer.future;
          }
          return jsonResponse(messageJson('ACCEPT', response: 'Second reply'));
        }),
      );

      // Send first message, waiting on completer
      await send(tester, 'First message in flight');
      expect(find.text('First message in flight'), findsOneWidget);
      expect(find.text('Working on your message'), findsOneWidget);

      // Trigger New chat while send is in flight via shell app bar action
      await tester.tap(find.byTooltip('New chat'));
      await tester.pump();

      // Transcript is cleared immediately
      expect(find.text('First message in flight'), findsNothing);
      expect(
        find.text('Ask a study question, or get help with maths or code.'),
        findsOneWidget,
      );

      // Complete the in-flight request
      completer.complete(
        jsonResponse(messageJson('ACCEPT', response: 'Stale reply')),
      );
      await settle(tester);

      // The transcript stays empty (the stale reply was discarded)
      expect(find.text('Stale reply'), findsNothing);
      expect(
        find.text('Ask a study question, or get help with maths or code.'),
        findsOneWidget,
      );

      // Next send has empty history
      await send(tester, 'Second message');
      await settle(tester);

      final reqs = app.backend.requests
          .where((r) => r.url.path == '/v1/messages')
          .toList();
      expect(reqs.length, 2);
      final body2 = jsonDecode(reqs[1].body) as Map<String, dynamic>;
      expect(body2['text'], 'Second message');
      expect(body2.containsKey('history'), isFalse);
    },
  );

  testWidgets(
    'tapping New chat while regenerate is in flight drops stale error banner',
    (tester) async {
      final completer = Completer<http.Response>();
      await pumpApp(
        tester,
        backend: backendWith((request) {
          return jsonResponse(messageJson('ACCEPT', response: 'Initial reply'));
        })..on('POST', '/v1/runs/run-1/regenerate', (_) => completer.future),
      );

      // 1. First POST /v1/messages returns an ACCEPT reply.
      await send(tester, 'First message');
      await settle(tester);
      expect(find.text('Initial reply'), findsOneWidget);

      // 2. Tap the reply's regenerate action while regenerate is in flight.
      await tester.tap(find.byTooltip('Regenerate response'));
      await tester.pump();

      // 3. Tap New chat and pump.
      await tester.tap(find.byTooltip('New chat'));
      await tester.pump();

      // 4. Complete the regenerate completer with an error response.
      completer.complete(http.Response('{}', 500));
      await settle(tester);

      // 5. Expect no stale error banner and empty state is shown.
      expect(find.text("Couldn't regenerate reply"), findsNothing);
      expect(
        find.text('Ask a study question, or get help with maths or code.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'tapping New chat while feedback is in flight drops stale error banner',
    (tester) async {
      final completer = Completer<http.Response>();
      await pumpApp(
        tester,
        backend: backendWith((request) {
          return jsonResponse(messageJson('ACCEPT', response: 'Initial reply'));
        })..on('POST', '/v1/runs/run-1/feedback', (_) => completer.future),
      );

      // 1. First message returns reply.
      await send(tester, 'First message');
      await settle(tester);
      expect(find.text('Initial reply'), findsOneWidget);

      // 2. Tap feedback (thumbs down) while feedback is in flight.
      await tester.tap(find.byTooltip('Thumbs down'));
      await tester.pump();

      // 3. Tap New chat and pump.
      await tester.tap(find.byTooltip('New chat'));
      await tester.pump();

      // 4. Complete the feedback completer with an error response.
      completer.complete(http.Response('{}', 500));
      await settle(tester);

      // 5. Expect no stale error banner and empty state is shown.
      expect(find.text("Couldn't send feedback"), findsNothing);
      expect(
        find.text('Ask a study question, or get help with maths or code.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'ChatController.newChat clears entries and pending in ChatScreen',
    (tester) async {
      final controller = ChatController();
      addTearDown(controller.dispose);
      final reply = Completer<http.Response>();
      final backend = backendWith((_) => reply.future);
      final api = KarmiApi(
        baseUrl: 'http://karmi.test',
        client: backend.client,
      );

      await pumpHost(
        tester,
        Scaffold(
          body: ChatScreen(api: api, controller: controller),
        ),
      );

      await send(tester, 'Testing controller');
      expect(find.text('Testing controller'), findsOneWidget);

      controller.newChat();
      await tester.pump();

      expect(find.text('Testing controller'), findsNothing);
      expect(
        find.text('Ask a study question, or get help with maths or code.'),
        findsOneWidget,
      );

      reply.complete(
        jsonResponse(messageJson('ACCEPT', response: 'Discarded')),
      );
      await settle(tester);
      expect(find.text('Discarded'), findsNothing);
    },
  );

  test(
    'buildHistoryFromEntries safely truncates without splitting UTF-16 surrogate pair',
    () {
      // 7999 'a's followed by a 2-code-unit emoji ('\u{1F600}').
      // Index 7999 is 0xD83D (high surrogate), index 8000 is 0xDE00 (low surrogate).
      final straddlingText = '${'a' * 7999}\u{1F600}';
      expect(straddlingText.length, 8001);
      expect(straddlingText.codeUnitAt(7999), 0xD83D);
      expect(
        straddlingText.codeUnitAt(7999) >= 0xD800 &&
            straddlingText.codeUnitAt(7999) <= 0xDBFF,
        isTrue,
      );

      final entries = [
        UserEntry(
          id: 'u1',
          text: straddlingText,
          idempotencyKey: 'k1',
          state: SendState.sent,
        ),
        ReplyEntry(
          id: 'r1',
          message: MessageView.fromJson(
            messageJson('ACCEPT', response: 'reply'),
          ),
        ),
      ];

      final history = buildHistoryFromEntries(entries);
      expect(history.length, 2);
      // User turn should be cut at 7999 instead of 8000, avoiding an orphaned high surrogate.
      expect(history[0].role, 'user');
      expect(history[0].content.length, 7999);
      expect(history[0].content, 'a' * 7999);

      // When emoji fits within 8000 (starts at 7998), both surrogates are preserved.
      final fittingText = '${'a' * 7998}\u{1F600}';
      expect(fittingText.length, 8000);
      final fittingEntries = [
        UserEntry(
          id: 'u2',
          text: fittingText,
          idempotencyKey: 'k2',
          state: SendState.sent,
        ),
        ReplyEntry(
          id: 'r2',
          message: MessageView.fromJson(
            messageJson('ACCEPT', response: 'reply'),
          ),
        ),
      ];
      final fittingHistory = buildHistoryFromEntries(fittingEntries);
      expect(fittingHistory[0].content.length, 8000);
      expect(fittingHistory[0].content, fittingText);

      // Also verify assistant response safe truncation.
      final assistantStraddling = [
        UserEntry(
          id: 'u3',
          text: 'hello',
          idempotencyKey: 'k3',
          state: SendState.sent,
        ),
        ReplyEntry(
          id: 'r3',
          message: MessageView.fromJson(
            messageJson('ACCEPT', response: straddlingText),
          ),
        ),
      ];
      final assistantHistory = buildHistoryFromEntries(assistantStraddling);
      expect(assistantHistory[1].role, 'assistant');
      expect(assistantHistory[1].content.length, 7999);
      expect(assistantHistory[1].content, 'a' * 7999);
    },
  );

  test(
    'truncateHistoryContent cuts at 7999 if high surrogate is at index 7999',
    () {
      final straddling = '${'x' * 7999}\u{1F389}';
      expect(truncateHistoryContent(straddling), 'x' * 7999);
      expect(
        truncateHistoryContent('${'x' * 7998}\u{1F389}'),
        '${'x' * 7998}\u{1F389}',
      );
      expect(truncateHistoryContent('x' * 8005), 'x' * 8000);
    },
  );
}
