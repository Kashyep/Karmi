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

  group('notes', () {
    test('listNotes parses id/content/version', () async {
      backend.on(
        'GET',
        '/v1/notes',
        (_) => jsonResponse([
          {'id': 'n1', 'content': 'a', 'version': 3},
        ]),
      );
      final notes = await api.listNotes();
      expect(notes.single.id, 'n1');
      expect(notes.single.version, 3);
    });

    test('createNote sends content and idempotency key; accepts 201', () async {
      backend.on(
        'POST',
        '/v1/notes',
        (_) => jsonResponse({'id': 'n2', 'content': 'b', 'version': 1}, 201),
      );
      final note = await api.createNote('b', idempotencyKey: 'note-key-1');
      expect(note.id, 'n2');
      expect(jsonDecode(backend.requests.single.body), {
        'content': 'b',
        'idempotency_key': 'note-key-1',
      });
    });

    test('deleteNote accepts 204 with an empty body', () async {
      backend.on('DELETE', '/v1/notes/n1', (_) => http.Response('', 204));
      await api.deleteNote('n1');
      expect(backend.requests.single.method, 'DELETE');
    });

    test('deleteNote 404 throws ServerException', () async {
      backend.on(
        'DELETE',
        '/v1/notes/n1',
        (_) => jsonResponse({'detail': 'note not found'}, 404),
      );
      await expectLater(api.deleteNote('n1'), throwsA(isA<ServerException>()));
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
}
