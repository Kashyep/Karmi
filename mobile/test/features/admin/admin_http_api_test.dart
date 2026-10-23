import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_http_api.dart';

HttpAdminApi _api(http.Client client) => HttpAdminApi(
  baseUrl: 'https://api.test',
  client: client,
  tokenProvider: () async => 'bearer-1',
);

void main() {
  test('probe maps 403 to AdminForbidden', () async {
    final api = _api(
      MockClient((_) async => http.Response('{"detail":"no"}', 403)),
    );
    expect(api.probe(), throwsA(isA<AdminForbidden>()));
  });

  test('probe accepts 401 ADMIN_SESSION_REQUIRED as eligible', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          '{"detail":{"code":"ADMIN_SESSION_REQUIRED"}}',
          401,
        ),
      ),
    );
    await api.probe();
  });

  test('probe accepts 200 {valid:false} as eligible', () async {
    final api = _api(
      MockClient((_) async => http.Response('{"valid":false}', 200)),
    );
    await api.probe();
  });

  test('probe 403 ADMIN_FORBIDDEN maps to AdminForbidden', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          '{"detail":{"code":"ADMIN_FORBIDDEN"}}',
          403,
        ),
      ),
    );
    await expectLater(api.probe(), throwsA(isA<AdminForbidden>()));
  });

  test('probe 401 with another code is not eligible', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          '{"detail":{"code":"INVALID_TOKEN"}}',
          401,
        ),
      ),
    );
    await expectLater(api.probe(), throwsA(isA<AdminUnauthorized>()));
  });

  test('423 with top-level retry_after maps to AdminLockedOut', () async {
    final api = _api(
      MockClient((_) async => http.Response('{"retry_after":90}', 423)),
    );
    await expectLater(
      api.openSession('000000'),
      throwsA(
        isA<AdminLockedOut>().having(
          (e) => e.retryAfter,
          'retryAfter',
          const Duration(seconds: 90),
        ),
      ),
    );
  });

  test('openSession 423 maps to AdminLockedOut with retry_after', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          '{"detail":{"code":"LOCKED","retry_after":120}}',
          423,
        ),
      ),
    );
    await expectLater(
      api.openSession('000000'),
      throwsA(
        isA<AdminLockedOut>().having(
          (e) => e.retryAfter,
          'retryAfter',
          const Duration(seconds: 120),
        ),
      ),
    );
  });

  test('openSession parses token and expiry', () async {
    final api = _api(
      MockClient(
        (req) async => http.Response(
          jsonEncode({
            'admin_session_token': 'tok',
            'expires_at': '2030-01-01T00:00:00Z',
          }),
          200,
        ),
      ),
    );
    final grant = await api.openSession('123456');
    expect(grant.token, 'tok');
    expect(grant.expiresAt.toUtc().year, 2030);
  });

  test('401 on a call maps to AdminUnauthorized', () async {
    final api = _api(MockClient((_) async => http.Response('{}', 401)));
    expect(
      api.monitor('tok'),
      throwsA(isA<AdminUnauthorized>()),
    );
  });

  test('exportUser sends reason as query and returns pretty JSON', () async {
    late Uri seen;
    final api = _api(
      MockClient((req) async {
        seen = req.url;
        expect(req.headers['X-Admin-Session'], 'tok');
        return http.Response('{"id":"u1"}', 200);
      }),
    );
    final out = await api.exportUser('tok', 'u1', reason: 'support ticket 9');
    expect(seen.path, '/v1/admin/users/u1/export');
    expect(seen.queryParameters['reason'], 'support ticket 9');
    expect(out, contains('\n'));
    expect(jsonDecode(out), {'id': 'u1'});
  });

  test('deleteUser sends reason and DELETE confirmation', () async {
    late Map<String, dynamic> body;
    final api = _api(
      MockClient((req) async {
        expect(req.method, 'DELETE');
        body = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response('', 204);
      }),
    );
    await api.deleteUser('tok', 'u1', reason: 'gdpr');
    expect(body, {'reason': 'gdpr', 'confirm': 'DELETE'});
  });
}
