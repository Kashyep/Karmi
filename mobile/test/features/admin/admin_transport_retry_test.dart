import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_http_api.dart';

/// Shared script for every client an [HttpAdminApi] creates. Each `send`
/// consumes one step: an [Exception] is thrown, a [http.Response] is returned,
/// and [_hang] never completes. All methods are logged in order.
class _Script {
  _Script(this.steps);

  final List<Object> steps;
  final methods = <String>[];
}

const _hang = Object();

class _ScriptedClient extends http.BaseClient {
  _ScriptedClient(this.script);

  final _Script script;
  bool closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    script.methods.add(request.method);
    final step = script.steps.removeAt(0);
    if (identical(step, _hang)) {
      return Completer<http.StreamedResponse>().future;
    }
    if (step is Exception) return Future.error(step);
    final resp = step as http.Response;
    return Future.value(
      http.StreamedResponse(
        http.ByteStream.fromBytes(resp.bodyBytes),
        resp.statusCode,
        headers: resp.headers,
      ),
    );
  }

  @override
  void close() {
    closed = true;
    super.close();
  }
}

Map<String, dynamic> _fixture(String name) {
  final raw = File('test/features/admin/fixtures/$name').readAsStringSync();
  return jsonDecode(raw) as Map<String, dynamic>;
}

/// Returns the api plus the list of clients the retry factory produced.
({HttpAdminApi api, List<_ScriptedClient> retryClients}) _api(
  _Script script, {
  Duration timeout = const Duration(seconds: 20),
}) {
  final retryClients = <_ScriptedClient>[];
  final api = HttpAdminApi(
    baseUrl: 'https://api.test',
    client: _ScriptedClient(script),
    tokenProvider: () async => 'bearer-1',
    timeout: timeout,
    retryClientFactory: () {
      final c = _ScriptedClient(script);
      retryClients.add(c);
      return c;
    },
  );
  return (api: api, retryClients: retryClients);
}

http.Response _usersPage() {
  final fixture = _fixture('users_list_limit25.json');
  return http.Response(
    jsonEncode(fixture['body']),
    fixture['status']! as int,
    headers: {'content-type': 'application/json'},
  );
}

void main() {
  test(
    'listUsers recovers from a stale pooled socket via a fresh client',
    () async {
      final script = _Script([
        http.ClientException('Connection closed before full header'),
        _usersPage(),
      ]);
      final h = _api(script);

      final page = await h.api.listUsers('tok');

      expect(page.items, isNotEmpty);
      expect(script.methods, ['GET', 'GET']);
      expect(h.retryClients, hasLength(1));
      expect(h.retryClients.single.closed, isTrue);
    },
  );

  test(
    'GET keeps failing at transport level: one retry, network kind',
    () async {
      final script = _Script([
        http.ClientException('reset'),
        http.ClientException('reset'),
      ]);
      final h = _api(script);

      await expectLater(
        h.api.listUsers('tok'),
        throwsA(
          isA<AdminFailure>().having(
            (e) => e.kind,
            'kind',
            AdminFailureKind.network,
          ),
        ),
      );
      expect(script.methods, ['GET', 'GET']);
    },
  );

  test('GET timeouts are retried once and map to timeout kind', () async {
    final script = _Script([_hang, _hang]);
    final h = _api(script, timeout: const Duration(milliseconds: 10));

    await expectLater(
      h.api.listUsers('tok'),
      throwsA(
        isA<AdminFailure>().having(
          (e) => e.kind,
          'kind',
          AdminFailureKind.timeout,
        ),
      ),
    );
    expect(script.methods, ['GET', 'GET']);
  });

  test('a hung token provider maps to timeout without sending', () async {
    final script = _Script([]);
    final api = HttpAdminApi(
      baseUrl: 'https://api.test',
      client: _ScriptedClient(script),
      tokenProvider: () => Completer<String?>().future,
      timeout: const Duration(milliseconds: 10),
    );

    await expectLater(
      api.listUsers('tok'),
      throwsA(
        isA<AdminFailure>().having(
          (e) => e.kind,
          'kind',
          AdminFailureKind.timeout,
        ),
      ),
    );
    expect(script.methods, isEmpty);
  });

  test('POST openSession is not retried on transport failure', () async {
    final script = _Script([
      http.ClientException('Connection closed before full header'),
      http.Response('{}', 200),
    ]);
    final h = _api(script);

    await expectLater(
      h.api.openSession('123456'),
      throwsA(
        isA<AdminFailure>().having(
          (e) => e.kind,
          'kind',
          AdminFailureKind.network,
        ),
      ),
    );
    expect(script.methods, ['POST']);
    expect(h.retryClients, isEmpty);
  });

  test('DELETE closeSession is not retried on transport failure', () async {
    final script = _Script([
      http.ClientException('Connection closed before full header'),
      http.Response('', 204),
    ]);
    final h = _api(script);

    await expectLater(h.api.closeSession('tok'), throwsA(isA<AdminFailure>()));
    expect(script.methods, ['DELETE']);
    expect(h.retryClients, isEmpty);
  });

  test('GET HTTP 500 is not retried and maps to server kind', () async {
    final script = _Script([http.Response('{"detail":"boom"}', 500)]);
    final h = _api(script);

    await expectLater(
      h.api.monitor('tok'),
      throwsA(
        isA<AdminFailure>()
            .having((e) => e.kind, 'kind', AdminFailureKind.server)
            .having((e) => e.statusCode, 'statusCode', 500),
      ),
    );
    expect(script.methods, ['GET']);
  });
}
