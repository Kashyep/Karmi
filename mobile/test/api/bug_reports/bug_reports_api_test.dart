import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/bug_reports/bug_report_errors.dart';
import 'package:karmi_app/api/bug_reports/bug_report_models.dart';
import 'package:karmi_app/api/bug_reports/bug_reports_api.dart';

void main() {
  group('BugReportsApi client methods and wire format', () {
    const baseUrl = 'https://api.karmi.test';
    const reportId = '550e8400-e29b-41d4-a716-446655440000';

    final testRequest = BugReportCreateRequest(
      clientReportId: reportId,
      category: BugReportCategory.chat,
      description: 'The response stopped mid-generation',
      diagnostics: const BugReportDiagnostics(
        appVersion: '0.1.0',
        buildNumber: '5',
        screen: 'chat',
      ),
    );

    test(
      'submitReport sends POST /v1/bug-reports with correct JSON and headers',
      () async {
        final mockClient = MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/v1/bug-reports');
          expect(request.headers['Content-Type'], 'application/json');
          expect(request.headers['Authorization'], 'Bearer test-token');

          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['client_report_id'], reportId);
          expect(body['category'], 'chat');
          expect(body['description'], 'The response stopped mid-generation');
          expect(body['diagnostics']['screen'], 'chat');

          return http.Response(
            jsonEncode({
              'id': 'rpt-1234',
              'ticket': 'KARMI-0042',
              'status': 'new',
              'created_at': '2026-11-07T12:00:00Z',
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        });

        final api = BugReportsApi(
          baseUrl: baseUrl,
          client: mockClient,
          tokenProvider: () async => 'test-token',
        );

        final result = await api.submitReport(testRequest);
        expect(result.id, 'rpt-1234');
        expect(result.ticket, 'KARMI-0042');
        expect(result.status, 'new');
      },
    );

    test('submitReport handles 200 OK replay idempotently', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'id': 'rpt-1234',
            'ticket': 'KARMI-0042',
            'status': 'triaged',
            'created_at': '2026-11-07T12:00:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);

      final result = await api.submitReport(testRequest);
      expect(result.ticket, 'KARMI-0042');
      expect(result.status, 'triaged');
    });

    test('submitReport throws BugReportConflictException on 409', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'idempotency conflict'}),
          409,
        );
      });

      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
      expect(
        () => api.submitReport(testRequest),
        throwsA(isA<BugReportConflictException>()),
      );
    });

    test(
      'submitReport throws BugReportRateLimitException with Retry-After on 429',
      () async {
        final mockClient = MockClient((request) async {
          return http.Response(
            jsonEncode({'detail': 'rate limit exceeded'}),
            429,
            headers: {'retry-after': '3600'},
          );
        });

        final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
        try {
          await api.submitReport(testRequest);
          fail('Expected BugReportRateLimitException');
        } on BugReportRateLimitException catch (e) {
          expect(e.retryAfterSeconds, 3600);
        }
      },
    );

    test(
      'submitReport throws BugReportPayloadTooLargeException on 413',
      () async {
        final mockClient = MockClient((request) async {
          return http.Response(
            jsonEncode({'detail': 'screenshot exceeds 5 MB'}),
            413,
          );
        });

        final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
        expect(
          () => api.submitReport(testRequest),
          throwsA(isA<BugReportPayloadTooLargeException>()),
        );
      },
    );

    test(
      'submitReport throws BugReportUnsupportedMediaTypeException on 415',
      () async {
        final mockClient = MockClient((request) async {
          return http.Response(
            jsonEncode({'detail': 'unsupported media type'}),
            415,
          );
        });

        final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
        expect(
          () => api.submitReport(testRequest),
          throwsA(isA<BugReportUnsupportedMediaTypeException>()),
        );
      },
    );

    test('submitReport throws BugReportValidationException on 422', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'validation failed for field description'}),
          422,
        );
      });

      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
      expect(
        () => api.submitReport(testRequest),
        throwsA(isA<BugReportValidationException>()),
      );
    });

    test(
      'getReport sends GET /v1/bug-reports/{id} and parses details',
      () async {
        final mockClient = MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/v1/bug-reports/rpt-1234');

          return http.Response(
            jsonEncode({
              'id': 'rpt-1234',
              'ticket': 'KARMI-0001',
              'category': 'chat',
              'description': 'Message got stuck',
              'diagnostics': {'screen': 'chat'},
              'status': 'new',
              'has_screenshot': true,
              'created_at': '2026-11-07T10:00:00Z',
              'updated_at': '2026-11-07T10:00:00Z',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        });

        final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
        final detail = await api.getReport('rpt-1234');

        expect(detail.id, 'rpt-1234');
        expect(detail.ticket, 'KARMI-0001');
        expect(detail.hasScreenshot, isTrue);
        expect(detail.category, 'chat');
      },
    );

    test('getReport throws BugReportNotFoundException on 404', () async {
      final mockClient = MockClient((request) async {
        return http.Response(jsonEncode({'detail': 'not found'}), 404);
      });

      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
      expect(
        () => api.getReport('rpt-none'),
        throwsA(isA<BugReportNotFoundException>()),
      );
    });
  });
}
