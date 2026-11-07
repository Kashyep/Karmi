import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_http_api.dart';

/// Fixtures are real `/v1/admin/*` responses captured from the live server
/// (karmi-beta, karmi_dev_admin) with emails, names, ids, and tokens replaced
/// by placeholders. Each file is `{"status": int, "body": <json>}`.
Map<String, dynamic> _fixture(String name) {
  final raw = File('test/features/admin/fixtures/$name').readAsStringSync();
  return jsonDecode(raw) as Map<String, dynamic>;
}

HttpAdminApi _apiReturning(
  Object body, {
  int status = 200,
  void Function(http.Request)? onRequest,
}) => HttpAdminApi(
  baseUrl: 'https://api.test',
  client: MockClient((req) async {
    onRequest?.call(req);
    return http.Response(
      body is String ? body : jsonEncode(body),
      status,
      headers: {'content-type': 'application/json'},
    );
  }),
  tokenProvider: () async => 'bearer-1',
);

HttpAdminApi _fromFixture(
  String name, {
  void Function(http.Request)? onRequest,
}) {
  final f = _fixture(name);
  return _apiReturning(
    f['body']!,
    status: f['status']! as int,
    onRequest: onRequest,
  );
}

void main() {
  group('session', () {
    test('probe without X-Admin-Session accepts 200 {valid:false}', () async {
      final f = _fixture('session_probe_without_admin_session.json');
      expect(f['status'], 200);
      expect(f['body'], {'valid': false, 'expires_at': null});
      await _fromFixture('session_probe_without_admin_session.json').probe();
    });

    test('probe with X-Admin-Session accepts 200 {valid:true}', () async {
      String? sent;
      final api = _fromFixture(
        'session_probe_with_admin_session.json',
        onRequest: (r) => sent = r.headers['X-Admin-Session'],
      );
      await api.probe();
      expect(_fixture('session_probe_with_admin_session.json')['body'], {
        'valid': true,
        'expires_at': isA<String>(),
      });
      expect(sent, isNull, reason: 'probe must not send X-Admin-Session');
    });

    test('probe with a bogus X-Admin-Session is still eligible', () async {
      await _fromFixture('session_probe_bogus_admin_session.json').probe();
    });

    test(
      'probe without bearer is 401 detail string, not ADMIN_SESSION_REQUIRED',
      () async {
        final f = _fixture('session_probe_no_bearer.json');
        expect(f['status'], 401);
        expect(f['body'], {'detail': 'authentication required'});
        await expectLater(
          _fromFixture('session_probe_no_bearer.json').probe(),
          throwsA(isA<AdminUnauthorized>()),
        );
      },
    );

    test('open session parses token and UTC expiry', () async {
      final f = _fixture('session_open.json');
      expect(f['body'], {
        'admin_session_token': 'PLACEHOLDER_ADMIN_SESSION_TOKEN',
        'expires_at': isA<String>(),
      });
      final grant = await _fromFixture(
        'session_open.json',
      ).openSession('000000');
      expect(grant.token, 'PLACEHOLDER_ADMIN_SESSION_TOKEN');
      expect(grant.expiresAt.isUtc, isTrue);
      expect(grant.expiresAt.year, 2026);
    });

    test('close session accepts {signed_out:true}', () async {
      expect(_fixture('session_delete.json')['body'], {'signed_out': true});
      await _fromFixture('session_delete.json').closeSession('tok');
    });

    test('probe after close reports valid:false with null expiry', () async {
      expect(_fixture('session_probe_after_close.json')['body'], {
        'valid': false,
        'expires_at': null,
      });
      await _fromFixture('session_probe_after_close.json').probe();
    });
  });

  group('users list', () {
    test('limit=25 page parses every AdminUser field', () async {
      String? query;
      final page = await _fromFixture(
        'users_list_limit25.json',
        onRequest: (r) => query = r.url.query,
      ).listUsers('tok');
      expect(query, 'limit=25');

      expect(page.items, hasLength(6));
      expect(page.nextCursor, isNull);

      final nulls = page.items.first;
      expect(nulls.id, isNotEmpty);
      expect(nulls.email, '');
      expect(nulls.displayName, 'Fixture User');
      expect(nulls.tier, 'ananta');
      expect(nulls.effectivePlan, 'ananta');
      expect(nulls.planExpiresAt, isNull);
      expect(nulls.revertPlanId, isNull);
      expect(nulls.testerLabel, isNull);
      expect(nulls.adminNotes, isNull, reason: 'list items omit admin_notes');
      expect(nulls.tester, isFalse);
      expect(nulls.disabled, isFalse);
      expect(nulls.createdAt, isNotNull);
      expect(nulls.lastActiveAt, isNull);

      final active = page.items.firstWhere((u) => u.lastActiveAt != null);
      expect(active.createdAt, isNotNull);
      expect(active.lastActiveAt!.isUtc, isTrue);
    });

    test('q with no match yields empty items and null cursor', () async {
      final page = await _fromFixture(
        'users_list_q_no_match.json',
      ).listUsers('tok', q: 'zzz-no-match');
      expect(page.items, isEmpty);
      expect(page.nextCursor, isNull);
    });

    test('tier filter page parses', () async {
      String? query;
      final page = await _fromFixture(
        'users_list_tier_ananta.json',
        onRequest: (r) => query = r.url.query,
      ).listUsers('tok', tier: 'ananta');
      expect(query, contains('tier=ananta'));
      expect(page.items, isNotEmpty);
      expect(page.items.every((u) => u.tier == 'ananta'), isTrue);
    });
  });

  group('user detail', () {
    test('usage user: nested usage numbers keep int vs double types', () async {
      final f = _fixture('user_detail_usage.json');
      final usage = (f['body'] as Map)['usage'] as Map;
      expect(usage['today_requests'], isA<int>());
      expect(usage['sessions'], isA<int>());
      expect(usage['month_spend_inr'], isA<double>());
      expect(usage['credits_remaining'], isA<double>());

      final detail = await _fromFixture(
        'user_detail_usage.json',
      ).getUser('tok', f['body']['id'] as String);
      expect(detail.user.id, f['body']['id']);
      expect(detail.user.adminNotes, isNull);
      expect(detail.usage.todayRequests, 11);
      expect(detail.usage.sessions, 4);
      expect(detail.usage.monthSpendInr, 0.0);
      expect(detail.usage.creditsRemaining, 0.02);
    });

    test('edge user: null plan, notes, and last_active fields', () async {
      final detail = await _fromFixture(
        'user_detail_edge_nulls.json',
      ).getUser('tok', 'x');
      expect(detail.user.email, '');
      expect(detail.user.testerLabel, isNull);
      expect(detail.user.adminNotes, isNull);
      expect(detail.user.planExpiresAt, isNull);
      expect(detail.user.revertPlanId, isNull);
      expect(detail.user.lastActiveAt, isNull);
      expect(detail.usage.todayRequests, 0);
      expect(detail.usage.sessions, 2);
      expect(detail.usage.monthSpendInr, 0.0);
    });

    test('export returns the JSON body as pretty text', () async {
      String? query;
      final text = await _fromFixture(
        'user_export_reason_test.json',
        onRequest: (r) => query = r.url.query,
      ).exportUser('tok', 'x', reason: 'test');
      expect(query, 'reason=test');
      final decoded = jsonDecode(text) as Map<String, dynamic>;
      expect(decoded['user'], isA<Map>());
      expect((decoded['user'] as Map)['email'], isNull);
      expect((decoded['user'] as Map)['tester_label'], isNull);
      expect((decoded['subscription'] as Map)['plan_id'], 'ananta');
      expect(decoded['runs'], isA<List>());
      expect(decoded['message_bodies_included'], isFalse);
    });
  });

  group('monitor', () {
    test('parses int counts and float rates', () async {
      final m = await _fromFixture('monitor.json').monitor('tok');
      expect(m.activeUsers, 4);
      expect(m.activeStreams, 0);
      expect(m.reqPerMin, 31.0);
      expect(m.errorRate, 0.0);
      expect(m.p95LatencyMs, 572.1);
      expect(m.spendTodayInr, 0.0);
      expect(m.platformBudgetInr, 1.0);
      expect(m.costTodayInr, 0.0);
      expect(m.requestsToday, 345);
      expect(m.dailyRequestCap, 2000);
      expect(m.successRate, 0.99);
      expect(m.openBugReports, 2);
      expect(m.modelHealth, hasLength(1));
      expect(m.modelHealth.single.model, 'claude-3-5-sonnet');
      expect(m.modelHealth.single.provider, 'anthropic');
      expect(m.modelHealth.single.runs, 100);
      expect(m.providerHealth, hasLength(1));
      expect(m.providerHealth.single.provider, 'openrouter');
      expect(m.providerHealth.single.status, 'ok');
      expect(m.generatedAt, isNotNull);
    });
  });
  group('audit', () {
    test('limit=50 page: int ids, object detail, null cursor', () async {
      String? query;
      final page = await _fromFixture(
        'audit_limit50.json',
        onRequest: (r) => query = r.url.query,
      ).audit('tok');
      expect(query, 'limit=50');
      expect(page.nextCursor, isNull);
      expect(page.items, hasLength(20));

      final exportEntry = page.items.firstWhere(
        (e) => e.action == 'user.export',
      );
      expect(exportEntry.id, '20', reason: 'int id stringified');
      expect(exportEntry.reason, 'test');
      expect(exportEntry.at, isNotNull);
      expect(exportEntry.targetUserId, isNotNull);
      expect(jsonDecode(exportEntry.detail!), {
        'conversations': 11,
        'runs': 13,
      });

      final viewEntry = page.items.firstWhere((e) => e.action == 'user.view');
      expect(viewEntry.reason, isNull);
      expect(jsonDecode(viewEntry.detail!), isEmpty);
    });
  });

  group('synthetic edge payloads', () {
    test('unknown extra fields are ignored at every level', () async {
      final body = {
        'items': [
          {
            'id': 'u1',
            'email': 'a@b.test',
            'display_name': 'N',
            'tier': 'ananta',
            'disabled': false,
            'brand_new_field': {'nested': true},
            'unlocked_tier': 2,
          },
        ],
        'next_cursor': 'abc',
        'extra_page_field': [1, 2, 3],
      };
      final page = await _apiReturning(body).listUsers('tok');
      expect(page.items.single.id, 'u1');
      expect(page.nextCursor, 'abc');

      final monitor = await _apiReturning({
        'active_users': 1,
        'surprise': 'x',
        'provider_health': [
          {'provider': 'p', 'status': 'ok', 'latency': 5},
        ],
      }).monitor('tok');
      expect(monitor.providerHealth.single.status, 'ok');
      expect(monitor.activeStreams, isNull);

      final audit = await _apiReturning({
        'items': [
          {
            'id': 9,
            'action': 'x',
            'detail': {'k': 'v'},
            'unknown': 1,
          },
        ],
        'next_cursor': null,
      }).audit('tok');
      expect(audit.items.single.id, '9');
      expect(jsonDecode(audit.items.single.detail!), {'k': 'v'});
    });

    test('nulls everywhere parse to defaults without throwing', () async {
      final user = {
        'id': 'u-null',
        'email': null,
        'display_name': null,
        'tester': null,
        'tester_label': null,
        'tier': null,
        'effective_plan': null,
        'plan_expires_at': null,
        'revert_plan_id': null,
        'unlocked_tier': null,
        'disabled': null,
        'created_at': null,
        'last_active_at': null,
      };
      final page = await _apiReturning({
        'items': [user],
        'next_cursor': null,
      }).listUsers('tok');
      final u = page.items.single;
      expect(u.id, 'u-null');
      expect(u.email, '');
      expect(u.displayName, '');
      expect(u.tier, '');
      expect(u.tester, isFalse);
      expect(u.disabled, isFalse);
      expect(u.effectivePlan, isNull);
      expect(u.revertPlanId, isNull);
      expect(u.createdAt, isNull);

      final detail = await _apiReturning({
        ...user,
        'admin_notes': null,
        'usage': {
          'today_requests': null,
          'month_spend_inr': null,
          'credits_remaining': null,
          'sessions': null,
        },
      }).getUser('tok', 'u-null');
      expect(detail.usage.todayRequests, isNull);
      expect(detail.usage.monthSpendInr, isNull);
      expect(detail.usage.creditsRemaining, isNull);
      expect(detail.usage.sessions, isNull);
      expect(detail.user.adminNotes, isNull);

      final monitor = await _apiReturning({
        'active_users': null,
        'active_streams': null,
        'req_per_min': null,
        'error_rate': null,
        'p95_latency_ms': null,
        'spend_today_inr': null,
        'platform_budget_inr': null,
        'cost_today_inr': null,
        'requests_today': null,
        'daily_request_cap': null,
        'success_rate': null,
        'open_bug_reports': null,
        'model_health': null,
        'provider_health': null,
        'generated_at': null,
      }).monitor('tok');
      expect(monitor.activeUsers, isNull);
      expect(monitor.reqPerMin, isNull);
      expect(monitor.providerHealth, isEmpty);
      expect(monitor.generatedAt, isNull);

      final audit = await _apiReturning({
        'items': [
          {
            'id': 1,
            'at': null,
            'admin_user_id': null,
            'action': null,
            'target_user_id': null,
            'reason': null,
            'detail': null,
          },
        ],
        'next_cursor': null,
      }).audit('tok');
      final e = audit.items.single;
      expect(e.id, '1');
      expect(e.action, '');
      expect(e.detail, isNull);
      expect(e.reason, isNull);
    });

    test('empty items list yields empty page', () async {
      final page = await _apiReturning({
        'items': <Object>[],
        'next_cursor': null,
      }).audit('tok');
      expect(page.items, isEmpty);
      expect(page.nextCursor, isNull);
    });

    test('renamed JSON keys parse and old *_usd keys are NOT read', () async {
      final detail = await _apiReturning({
        'id': 'u1',
        'usage': {
          'month_spend_usd': 99.0,
          'month_spend_inr': 42.0,
          'credits_remaining': 10.0,
        },
      }).getUser('tok', 'u1');
      expect(detail.usage.monthSpendInr, 42.0);

      final detailOldOnly = await _apiReturning({
        'id': 'u2',
        'usage': {'month_spend_usd': 99.0, 'credits_remaining': 10.0},
      }).getUser('tok', 'u2');
      expect(detailOldOnly.usage.monthSpendInr, isNull);

      final monitor = await _apiReturning({
        'spend_today_usd': 99.0,
        'platform_budget_usd': 99.0,
        'spend_today_inr': 15.0,
        'platform_budget_inr': 500.0,
        'cost_today_inr': 15.0,
      }).monitor('tok');
      expect(monitor.spendTodayInr, 15.0);
      expect(monitor.platformBudgetInr, 500.0);
      expect(monitor.costTodayInr, 15.0);

      final monitorOldOnly = await _apiReturning({
        'spend_today_usd': 99.0,
        'platform_budget_usd': 99.0,
      }).monitor('tok');
      expect(monitorOldOnly.spendTodayInr, isNull);
      expect(monitorOldOnly.platformBudgetInr, isNull);
      expect(monitorOldOnly.costTodayInr, isNull);
    });
  });
}
