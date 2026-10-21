import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/karmi_api.dart';

import '../support/fake_backend.dart';

void main() {
  late FakeBackend backend;
  late KarmiApi api;

  setUp(() {
    backend = FakeBackend();
    api = backend.api();
  });

  group('sendMessage', () {
    test('loads a fresh bearer token for each authenticated request', () async {
      final tokens = ['clerk-token-1', 'clerk-token-2'];
      backend.on('GET', '/v1/tasks', (_) => jsonResponse([]));
      api.token = 'stale-development-token';
      api.tokenProvider = () async => tokens.removeAt(0);

      await api.listTasks();
      await api.listTasks();

      expect(
        backend.requests.map((request) => request.headers['Authorization']),
        ['Bearer clerk-token-1', 'Bearer clerk-token-2'],
      );
    });

    test(
      'does not fall back to a cached token when provider returns null',
      () async {
        backend.on('GET', '/v1/tasks', (_) => jsonResponse([]));
        api.token = 'stale-development-token';
        api.tokenProvider = () async => null;

        await api.listTasks();

        expect(
          backend.requests.single.headers,
          isNot(contains('Authorization')),
        );
      },
    );

    test('200 parses MessageView and sends bearer + idempotency key', () async {
      backend.on(
        'POST',
        '/v1/messages',
        (_) => jsonResponse(messageJson('ASK_USER')),
      );
      final view = await api.sendMessage('hi', idempotencyKey: 'key-12345678');
      expect(view.outcome, Outcome.askUser);
      expect(view.response, 'Draft ready: plan the week');
      final request = backend.requests.single;
      expect(request.headers['Authorization'], 'Bearer test-token');
      expect(jsonDecode(request.body), {
        'text': 'hi',
        'idempotency_key': 'key-12345678',
      });
    });

    test(
      'sendMessage includes history when non-empty, omits when empty or null',
      () async {
        backend.on(
          'POST',
          '/v1/messages',
          (_) => jsonResponse(messageJson('ACCEPT')),
        );
        // 1. Non-empty history
        await api.sendMessage(
          'how are you',
          idempotencyKey: 'k1',
          history: const [
            HistoryTurn(role: 'user', content: 'hello'),
            HistoryTurn(role: 'assistant', content: 'hi there'),
          ],
        );
        expect(jsonDecode(backend.requests[0].body), {
          'text': 'how are you',
          'idempotency_key': 'k1',
          'history': [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'hi there'},
          ],
        });

        // 2. Empty history
        await api.sendMessage(
          'test 2',
          idempotencyKey: 'k2',
          history: const [],
        );
        expect(jsonDecode(backend.requests[1].body), {
          'text': 'test 2',
          'idempotency_key': 'k2',
        });

        // 3. Null history
        await api.sendMessage('test 3', idempotencyKey: 'k3');
        expect(jsonDecode(backend.requests[2].body), {
          'text': 'test 3',
          'idempotency_key': 'k3',
        });
      },
    );

    test('every wire outcome maps to a lowerCamel member', () {
      const wire = {
        'ACCEPT': Outcome.accept,
        'REPAIR': Outcome.repair,
        'ESCALATE': Outcome.escalate,
        'ASK_USER': Outcome.askUser,
        'SAFE_STOP': Outcome.safeStop,
        'DEFERRED': Outcome.deferred,
      };
      for (final MapEntry(key: name, value: outcome) in wire.entries) {
        expect(Outcome.fromWire(name), outcome);
        expect(outcome.wireName, name);
      }
    });

    test(
      'unknown or missing outcome parses as unknown instead of throwing',
      () {
        expect(Outcome.fromWire('NEW_STATE'), Outcome.unknown);
        expect(Outcome.fromWire(null), Outcome.unknown);
        expect(Outcome.fromWire(''), Outcome.unknown);
        final view = MessageView.fromJson(messageJson('SOMETHING_NEW'));
        expect(view.outcome, Outcome.unknown);
      },
    );

    test('null route is accepted (schema: route: str | None)', () {
      final json = messageJson('ACCEPT')..['route'] = null;
      expect(MessageView.fromJson(json).route, isNull);
    });
    test('previous_run_id is parsed if present, null otherwise', () {
      final jsonWithPrev = messageJson('ACCEPT')
        ..['previous_run_id'] = 'run-prev-123';
      expect(MessageView.fromJson(jsonWithPrev).previousRunId, 'run-prev-123');

      final jsonWithoutPrev = messageJson('ACCEPT');
      expect(MessageView.fromJson(jsonWithoutPrev).previousRunId, isNull);
    });

    test('401 throws Unauthorized and notifies the session', () async {
      var notified = 0;
      api.onUnauthorized = () => notified++;
      backend.on(
        'POST',
        '/v1/messages',
        (_) => jsonResponse({'detail': 'invalid session'}, 401),
      );
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<UnauthorizedException>()),
      );
      expect(notified, 1);
    });

    test('409 in flight throws InFlight', () async {
      backend.on(
        'POST',
        '/v1/messages',
        (_) => jsonResponse({
          'detail': 'request already in flight; retry to observe its result',
        }, 409),
      );
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<InFlightException>()),
      );
    });

    test('409 payload mismatch throws IdempotencyConflict', () async {
      backend.on(
        'POST',
        '/v1/messages',
        (_) => jsonResponse({
          'detail': 'idempotency key was reused with a different payload',
        }, 409),
      );
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<IdempotencyConflictException>()),
      );
    });

    test(
      '429 ALLOWANCE_EXHAUSTED throws LimitReached with reset time',
      () async {
        backend.on(
          'POST',
          '/v1/messages',
          (_) => jsonResponse({
            'detail': {
              'code': 'ALLOWANCE_EXHAUSTED',
              'message': 'everyday allowance exhausted',
              'reset_at': '2026-09-27T00:00:00+00:00',
            },
          }, 429),
        );
        final error = await api
            .sendMessage('hi', idempotencyKey: 'key-12345678')
            .then<Object?>((_) => null, onError: (Object e) => e);
        expect(error, isA<LimitReachedException>());
        expect(
          (error! as LimitReachedException).resetAt,
          DateTime.utc(2026, 9, 27),
        );
      },
    );

    test(
      '429 BETA_CAPACITY_FULL throws BetaCapacityFull with reset time',
      () async {
        backend.on(
          'POST',
          '/v1/messages',
          (_) => jsonResponse({
            'detail': {
              'code': 'BETA_CAPACITY_FULL',
              'message': "Karmi's beta has reached today's limit.",
              'reset_at': '2026-10-22T00:00:00+00:00',
            },
          }, 429),
        );
        final error = await api
            .sendMessage('hi', idempotencyKey: 'key-12345678')
            .then<Object?>((_) => null, onError: (Object e) => e);
        expect(error, isA<BetaCapacityFullException>());
        expect(
          (error! as BetaCapacityFullException).resetAt,
          DateTime.utc(2026, 10, 22),
        );
      },
    );

    test('429 without the allowance code is a ServerException', () async {
      backend.on('POST', '/v1/messages', (_) => jsonResponse({}, 429));
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(
          isA<ServerException>().having((e) => e.statusCode, 'status', 429),
        ),
      );
    });

    test('socket error throws Network', () async {
      backend.on('POST', '/v1/messages', FakeBackend.network());
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<NetworkException>()),
      );
    });

    test('client exception throws Network', () async {
      backend.on(
        'POST',
        '/v1/messages',
        (_) => throw http.ClientException('connection reset'),
      );
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<NetworkException>()),
      );
    });

    test('default timeout outlasts two 12 s gateway attempts', () {
      expect(KarmiApi().timeout, const Duration(seconds: 60));
    });

    test('timeout throws Network', () async {
      final slow = KarmiApi(
        baseUrl: 'http://karmi.test',
        client: backend.client,
        timeout: const Duration(milliseconds: 20),
      );
      backend.on(
        'POST',
        '/v1/messages',
        (_) => Completer<http.Response>().future,
      );
      await expectLater(
        slow.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<NetworkException>()),
      );
    });

    test('500 throws ServerException', () async {
      backend.on('POST', '/v1/messages', (_) => http.Response('boom', 500));
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(
          isA<ServerException>().having((e) => e.statusCode, 'status', 500),
        ),
      );
    });

    test('malformed 200 body throws ServerException', () async {
      backend.on('POST', '/v1/messages', (_) => http.Response('<html>', 200));
      await expectLater(
        api.sendMessage('hi', idempotencyKey: 'key-12345678'),
        throwsA(isA<ServerException>()),
      );
    });
  });

  test('idempotency keys are 32 hex chars and unique', () {
    final keys = {for (var i = 0; i < 100; i++) KarmiApi.newIdempotencyKey()};
    expect(keys, hasLength(100));
    for (final key in keys) {
      expect(key, matches(RegExp(r'^[0-9a-f]{32}$')));
    }
  });

  test('default base URL is the emulator host loopback', () {
    expect(KarmiApi.defaultBaseUrl, 'http://10.0.2.2:8000');
  });

  group('dev token', () {
    test('POST /dev/token without Authorization returns the token', () async {
      backend.on(
        'POST',
        '/dev/token',
        (_) => jsonResponse({'token': 'abc', 'user_id': 'u1'}),
      );
      expect(await api.issueDevToken(), 'abc');
      expect(backend.requests.single.headers['Authorization'], isNull);
    });

    test('404 outside development throws ServerException(404)', () async {
      backend.on('POST', '/dev/token', (_) => jsonResponse({}, 404));
      await expectLater(
        api.issueDevToken(),
        throwsA(
          isA<ServerException>().having((e) => e.statusCode, 'status', 404),
        ),
      );
    });
  });

  group('tasks and usage', () {
    test('listTasks and completeTask', () async {
      backend
        ..on(
          'GET',
          '/v1/tasks',
          (_) => jsonResponse([
            {'id': 't1', 'title': 'x', 'completed': false},
          ]),
        )
        ..on(
          'PATCH',
          '/v1/tasks/t1/complete',
          (_) => jsonResponse({'id': 't1', 'title': 'x', 'completed': true}),
        );
      expect((await api.listTasks()).single.completed, isFalse);
      expect((await api.completeTask('t1')).completed, isTrue);
    });

    test('getUsage parses timestamps and the synthetic flag', () async {
      backend.on('GET', '/v1/usage', (_) => jsonResponse(usageJson(used: 5)));
      final usage = await api.getUsage();
      expect(usage.everydayUsed, 5);
      expect(usage.resetAt, DateTime.utc(2026, 9, 27));
      expect(usage.synthetic, isTrue);
    });
  });

  group('feedback and regenerate', () {
    test(
      'sendFeedback sends rating and reason; parses RunFeedbackView',
      () async {
        backend.on('POST', '/v1/runs/run-101/feedback', (req) {
          final body = jsonDecode(req.body) as Map<String, dynamic>;
          return jsonResponse({
            'run_id': 'run-101',
            'rating': body['rating'],
            'reason': body['reason'],
          });
        });

        final res = await api.sendFeedback(
          'run-101',
          rating: FeedbackRating.down,
          reason: 'too_slow',
        );
        expect(res.runId, 'run-101');
        expect(res.rating, FeedbackRating.down);
        expect(res.reason, 'too_slow');

        final req = backend.requests.single;
        expect(req.headers['Authorization'], 'Bearer test-token');
        expect(jsonDecode(req.body), {'rating': 'down', 'reason': 'too_slow'});
      },
    );

    test('sendFeedback without reason omits reason field', () async {
      backend.on(
        'POST',
        '/v1/runs/run-102/feedback',
        (_) => jsonResponse({'run_id': 'run-102', 'rating': 'up'}),
      );

      final res = await api.sendFeedback('run-102', rating: FeedbackRating.up);
      expect(res.runId, 'run-102');
      expect(res.rating, FeedbackRating.up);
      expect(res.reason, isNull);

      final req = backend.requests.single;
      expect(jsonDecode(req.body), {'rating': 'up'});
    });

    test(
      'regenerateRun sends idempotency_key and reason; parses MessageView with previous_run_id',
      () async {
        backend.on(
          'POST',
          '/v1/runs/run-200/regenerate',
          (_) => jsonResponse({
            ...messageJson('ACCEPT', response: 'Better response'),
            'run_id': 'run-201',
            'previous_run_id': 'run-200',
          }),
        );

        final view = await api.regenerateRun(
          'run-200',
          text: 'original prompt',
          idempotencyKey: 'regen-key-1',
          reason: 'wrong',
        );
        expect(view.runId, 'run-201');
        expect(view.previousRunId, 'run-200');
        expect(view.response, 'Better response');

        final req = backend.requests.single;
        expect(jsonDecode(req.body), {
          'text': 'original prompt',
          'idempotency_key': 'regen-key-1',
          'reason': 'wrong',
        });
      },
    );

    test(
      'regenerateRun includes history when non-empty, omits when empty or null',
      () async {
        backend.on(
          'POST',
          '/v1/runs/run-300/regenerate',
          (_) => jsonResponse(messageJson('ACCEPT')),
        );

        // With history
        await api.regenerateRun(
          'run-300',
          text: 'hello',
          idempotencyKey: 'k-regen-1',
          history: const [HistoryTurn(role: 'user', content: 'prev')],
        );
        expect(jsonDecode(backend.requests[0].body)['history'], [
          {'role': 'user', 'content': 'prev'},
        ]);

        // Without history
        await api.regenerateRun(
          'run-300',
          text: 'hello',
          idempotencyKey: 'k-regen-2',
        );
        expect(
          (jsonDecode(backend.requests[1].body) as Map).containsKey('history'),
          isFalse,
        );
      },
    );

    test('FeedbackRating wire parsing', () {
      expect(FeedbackRating.fromWire('up'), FeedbackRating.up);
      expect(FeedbackRating.fromWire('down'), FeedbackRating.down);
      expect(FeedbackRating.fromWire('invalid'), isNull);
      expect(FeedbackRating.fromWire(null), isNull);
    });
  });
}
