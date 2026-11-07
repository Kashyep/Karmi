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
        (_) async =>
            http.Response('{"detail":{"code":"ADMIN_SESSION_REQUIRED"}}', 401),
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
        (_) async =>
            http.Response('{"detail":{"code":"ADMIN_FORBIDDEN"}}', 403),
      ),
    );
    await expectLater(api.probe(), throwsA(isA<AdminForbidden>()));
  });

  test('probe 401 with another code is not eligible', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response('{"detail":{"code":"INVALID_TOKEN"}}', 401),
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
    expect(api.monitor('tok'), throwsA(isA<AdminUnauthorized>()));
  });

  test('exportUser sends reason as header and returns pretty JSON', () async {
    late Uri seen;
    late Map<String, String> seenHeaders;
    final api = _api(
      MockClient((req) async {
        seen = req.url;
        seenHeaders = req.headers;
        expect(req.headers['X-Admin-Session'], 'tok');
        return http.Response('{"id":"u1"}', 200);
      }),
    );
    final out = await api.exportUser('tok', 'u1', reason: 'support ticket 9');
    expect(seen.path, '/v1/admin/users/u1/export');
    expect(seen.queryParameters.containsKey('reason'), isFalse);
    expect(seenHeaders['X-Admin-Reason'], 'support ticket 9');
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

  test(
    '403 ADMIN_TARGET_PROTECTED is a failure, not console-hiding forbidden',
    () async {
      final api = _api(
        MockClient(
          (_) async => http.Response(
            '{"detail":{"code":"ADMIN_TARGET_PROTECTED","message":"admins cannot act on another admin"}}',
            403,
          ),
        ),
      );
      await expectLater(
        api.suspend('tok', 'u2', reason: 'abuse report'),
        throwsA(
          isA<AdminFailure>().having((e) => e.statusCode, 'statusCode', 403),
        ),
      );
    },
  );

  test('ADMIN_FORBIDDEN object detail still maps to AdminForbidden', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          '{"detail":{"code":"ADMIN_FORBIDDEN","message":"admin access denied"}}',
          403,
        ),
      ),
    );
    await expectLater(api.monitor('tok'), throwsA(isA<AdminForbidden>()));
  });

  test('audit page parses server shape: int ids and object detail', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'items': [
              {
                'id': 42,
                'at': '2026-10-24T09:15:00.123456+00:00',
                'admin_user_id': 'a1',
                'action': 'tier.change',
                'target_user_id': 'u1',
                'reason': 'support ticket',
                'detail': {
                  'before': {'plan_id': 'ananta'},
                  'after': {'plan_id': 'yanta'},
                },
              },
              {
                'id': 41,
                'at': '2026-10-24T09:00:00+00:00',
                'admin_user_id': 'a1',
                'action': 'admin.logout',
                'target_user_id': null,
                'reason': null,
                'detail': null,
              },
            ],
            'next_cursor': '41',
          }),
          200,
        ),
      ),
    );
    final page = await api.audit('tok');
    expect(page.nextCursor, '41');
    expect(page.items.first.id, '42');
    expect(jsonDecode(page.items.first.detail!), {
      'before': {'plan_id': 'ananta'},
      'after': {'plan_id': 'yanta'},
    });
    expect(page.items.last.detail, isNull);
    expect(page.items.last.targetUserId, isNull);
  });

  test('user detail parses server shape with nullable plan fields', () async {
    final api = _api(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'id': 'u1',
            'email': 'a@example.com',
            'display_name': 'Ada',
            'tester': true,
            'tester_label': 'beta-wave-1',
            'tier': 'yanta',
            'effective_plan': 'yanta',
            'plan_expires_at': '2026-11-24T00:00:00+00:00',
            'revert_plan_id': 'ananta',
            'unlocked_tier': 2,
            'disabled': false,
            'created_at': '2026-01-02T03:04:05.678901+00:00',
            'last_active_at': null,
            'admin_notes': null,
            'usage': {
              'today_requests': 3,
              'month_spend_inr': 0.123456,
              'credits_remaining': 4.5,
              'sessions': 7,
            },
          }),
          200,
        ),
      ),
    );
    final detail = await api.getUser('tok', 'u1');
    expect(detail.user.effectivePlan, 'yanta');
    expect(detail.user.planExpiresAt, isNotNull);
    expect(detail.user.revertPlanId, 'ananta');
    expect(detail.user.lastActiveAt, isNull);
    expect(detail.usage.todayRequests, 3);
    expect(detail.usage.monthSpendInr, closeTo(0.123456, 1e-9));
    expect(detail.usage.sessions, 7);
  });

  test('adjustCredits posts delta_inr and reason without *_usd', () async {
    Map<String, dynamic>? postedBody;
    final api = _api(
      MockClient((req) async {
        postedBody = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({'budget_inr': 100.0, 'credits_remaining': 50.0}),
          200,
        );
      }),
    );
    await api.adjustCredits('tok', 'u1', deltaInr: 25.5, reason: 'promotion');
    expect(postedBody, {'delta_inr': 25.5, 'reason': 'promotion'});
    expect(postedBody!.containsKey('delta_usd'), isFalse);
    expect(postedBody!.containsKey('budget_usd'), isFalse);
  });

  test('adjustCredits posts budget_inr and reason without *_usd', () async {
    Map<String, dynamic>? postedBody;
    final api = _api(
      MockClient((req) async {
        postedBody = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({'budget_inr': 500.0, 'credits_remaining': 200.0}),
          200,
        );
      }),
    );
    await api.adjustCredits('tok', 'u1', budgetInr: 500.0, reason: 'override');
    expect(postedBody, {'budget_inr': 500.0, 'reason': 'override'});
    expect(postedBody!.containsKey('delta_usd'), isFalse);
  });

  test('listBugReports sends query params and parses page', () async {
    Uri? sentUri;
    final api = _api(
      MockClient((req) async {
        sentUri = req.url;
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'b1',
                'ticket': 'KARMI-0001',
                'category': 'crash',
                'status': 'new',
                'description_preview': 'App crashes on start',
                'user_id': 'u1',
                'user_display_name': 'Test User',
                'has_screenshot': true,
                'created_at': '2026-10-24T00:00:00+00:00',
                'updated_at': '2026-10-24T01:00:00+00:00',
              },
            ],
            'next_cursor': 'cursor-123',
          }),
          200,
        );
      }),
    );
    final page = await api.listBugReports(
      'tok',
      status: 'new',
      category: 'crash',
      limit: 25,
      cursor: 'cur-prev',
    );
    expect(sentUri!.path, '/v1/admin/bug-reports');
    expect(sentUri!.queryParameters['status'], 'new');
    expect(sentUri!.queryParameters['category'], 'crash');
    expect(sentUri!.queryParameters['limit'], '25');
    expect(sentUri!.queryParameters['cursor'], 'cur-prev');
    expect(page.items, hasLength(1));
    expect(page.items.single.ticket, 'KARMI-0001');
    expect(page.items.single.hasScreenshot, isTrue);
    expect(page.nextCursor, 'cursor-123');
  });

  test(
    'getBugReport fetches detail and parses diagnostics and user summary',
    () async {
      final api = _api(
        MockClient((req) async {
          expect(req.url.path, '/v1/admin/bug-reports/b1');
          return http.Response(
            jsonEncode({
              'id': 'b1',
              'ticket': 'KARMI-0001',
              'category': 'chat',
              'status': 'triaged',
              'description': 'Chat stream froze midway',
              'diagnostics': {
                'app_version': '0.1.0',
                'os': 'android',
                'model': 'Pixel 9a',
              },
              'admin_notes': 'Investigating provider response',
              'has_screenshot': false,
              'user': {'id': 'u1', 'display_name': 'Alice', 'plan': 'ananta'},
              'created_at': '2026-10-24T00:00:00+00:00',
              'updated_at': '2026-10-24T01:00:00+00:00',
              'triaged_at': '2026-10-24T02:00:00+00:00',
              'resolved_at': null,
            }),
            200,
          );
        }),
      );
      final report = await api.getBugReport('tok', 'b1');
      expect(report.id, 'b1');
      expect(report.ticket, 'KARMI-0001');
      expect(report.diagnostics['app_version'], '0.1.0');
      expect(report.user?.displayName, 'Alice');
      expect(report.user?.plan, 'ananta');
      expect(report.triagedAt, isNotNull);
      expect(report.resolvedAt, isNull);
    },
  );

  test(
    'getBugReportScreenshot fetches raw bytes with auth and handles 404',
    () async {
      String? authHeader;
      final api = _api(
        MockClient((req) async {
          authHeader = req.headers['X-Admin-Session'];
          if (req.url.path == '/v1/admin/bug-reports/b1/screenshot') {
            return http.Response.bytes([1, 2, 3, 4], 200);
          }
          return http.Response('not found', 404);
        }),
      );
      final bytes = await api.getBugReportScreenshot('tok', 'b1');
      expect(bytes, [1, 2, 3, 4]);
      expect(authHeader, 'tok');

      await expectLater(
        api.getBugReportScreenshot('tok', 'b2'),
        throwsA(
          isA<AdminFailure>().having((e) => e.statusCode, 'statusCode', 404),
        ),
      );
    },
  );

  test(
    'patchBugReport sends only changed fields and handles 409 conflict',
    () async {
      Map<String, dynamic>? patchBody;
      final api = _api(
        MockClient((req) async {
          if (req.method == 'PATCH') {
            patchBody = jsonDecode(req.body) as Map<String, dynamic>;
            if (patchBody?['status'] == 'invalid_state') {
              return http.Response(
                jsonEncode({'detail': 'invalid status transition'}),
                409,
              );
            }
            return http.Response(
              jsonEncode({
                'id': 'b1',
                'ticket': 'KARMI-0001',
                'category': 'chat',
                'status': patchBody?['status'] ?? 'new',
                'description': 'description',
                'diagnostics': {},
                'admin_notes': patchBody?['admin_notes'],
                'has_screenshot': false,
                'created_at': '2026-10-24T00:00:00+00:00',
                'updated_at': '2026-10-24T01:00:00+00:00',
              }),
              200,
            );
          }
          return http.Response('', 400);
        }),
      );

      // Status only
      await api.patchBugReport(
        'tok',
        'b1',
        status: 'triaged',
        reason: 'triaged it',
      );
      expect(patchBody, {'status': 'triaged', 'reason': 'triaged it'});
      expect(patchBody!.containsKey('admin_notes'), isFalse);

      // Admin notes only
      await api.patchBugReport(
        'tok',
        'b1',
        adminNotes: 'note added',
        reason: 'added info',
      );
      expect(patchBody, {'admin_notes': 'note added', 'reason': 'added info'});
      expect(patchBody!.containsKey('status'), isFalse);

      // 409 conflict
      await expectLater(
        api.patchBugReport('tok', 'b1', status: 'invalid_state', reason: 'bad'),
        throwsA(
          isA<AdminFailure>().having((e) => e.statusCode, 'statusCode', 409),
        ),
      );
    },
  );
}
