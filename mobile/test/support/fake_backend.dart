import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

typedef Handler = FutureOr<http.Response> Function(http.Request request);

http.Response jsonResponse(Object? body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

Map<String, Object?> messageJson(
  String outcome, {
  String response = 'Draft ready: plan the week',
}) => {
  'run_id': 'run-1',
  'status': 'completed',
  'outcome': outcome,
  'response': response,
  'route': 'fake-economy',
};

Map<String, Object?> usageJson({int used = 3, int limit = 20}) => {
  'plan_id': 'ananta',
  'plan_label': 'Ananta',
  'everyday_used': used,
  'everyday_limit': limit,
  'reserved_micro': 0,
  'settled_micro': 1200,
  'spend_limit_micro': 20000,
  'reset_at': '2026-09-27T00:00:00Z',
  'period_reset_at': '2026-10-01T00:00:00Z',
  'policy_version': 'synthetic-v1',
  'synthetic': true,
};

/// Route table over [MockClient]. Unrouted requests fail the test with 599.
class FakeBackend {
  final Map<String, Handler> routes = {};
  final List<http.Request> requests = [];

  void on(String method, String path, Handler handler) =>
      routes['$method $path'] = handler;

  static Handler network() =>
      (_) => throw const SocketException('offline');

  http.Client get client => MockClient((request) async {
    requests.add(request);
    final handler = routes['${request.method} ${request.url.path}'];
    if (handler == null) return http.Response('unrouted', 599);
    return handler(request);
  });

  KarmiApi api({String? token = 'test-token'}) =>
      KarmiApi(baseUrl: 'http://karmi.test', client: client, token: token);

  /// Server-side armory state: enforces `active_theme <= unlocked_tier` like
  /// API-002 (403 TIER_LOCKED, 422 invalid).
  int unlockedTier = 1;
  int activeTheme = 1;

  Map<String, Object?> armoryJson() => {
    'unlocked_tier': unlockedTier,
    'active_theme': activeTheme,
    'tiers': [
      for (final t in KarmiTier.values)
        {'id': t.id, 'key': t.name, 'label': t.label, 'plan_id': t.planId},
    ],
  };

  void routeArmory() {
    on('GET', '/v1/armory', (_) {
      if (activeTheme > unlockedTier) activeTheme = unlockedTier;
      return jsonResponse(armoryJson());
    });
    on('PUT', '/v1/armory/active-theme', (request) {
      final value = (jsonDecode(request.body) as Map)['active_theme'];
      if (value is! int || value < 1 || value > 4) {
        return jsonResponse({'detail': 'invalid'}, 422);
      }
      if (value > unlockedTier) {
        return jsonResponse({
          'detail': {'code': 'TIER_LOCKED', 'unlocked_tier': unlockedTier},
        }, 403);
      }
      activeTheme = value;
      return jsonResponse(armoryJson());
    });
  }

  /// A backend where every read succeeds with realistic synthetic data.
  static FakeBackend healthy({
    KarmiTier unlocked = KarmiTier.ananta,
    KarmiTier active = KarmiTier.ananta,
  }) {
    final backend = FakeBackend()
      ..unlockedTier = unlocked.id
      ..activeTheme = active.id
      ..routeArmory();
    backend
      ..on(
        'POST',
        '/dev/token',
        (_) => jsonResponse({'token': 't', 'user_id': 'u'}),
      )
      ..on('GET', '/v1/usage', (_) => jsonResponse(usageJson()))
      ..on(
        'GET',
        '/v1/notes',
        (_) => jsonResponse([
          {'id': 'n1', 'content': 'Prefers short answers.', 'version': 1},
          {'id': 'n2', 'content': 'Timezone is Asia/Kolkata.', 'version': 1},
        ]),
      )
      ..on(
        'GET',
        '/v1/tasks',
        (_) => jsonResponse([
          {'id': 't1', 'title': 'Call the bank', 'completed': false},
          {'id': 't2', 'title': 'Renew passport', 'completed': true},
        ]),
      )
      ..on('POST', '/v1/messages', (_) => jsonResponse(messageJson('ACCEPT')));
    return backend;
  }
}
