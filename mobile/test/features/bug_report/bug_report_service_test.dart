import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/bug_reports/bug_report_models.dart';
import 'package:karmi_app/api/bug_reports/bug_reports_api.dart';
import 'package:karmi_app/features/bug_report/bug_report_queue.dart';
import 'package:karmi_app/features/bug_report/bug_report_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BugReportService submission lifecycle and queue handling', () {
    const baseUrl = 'https://api.karmi.test';
    const reportId = '550e8400-e29b-41d4-a716-446655440000';

    final testRequest = BugReportCreateRequest(
      clientReportId: reportId,
      category: BugReportCategory.chat,
      description: 'Stream stopped abruptly',
      diagnostics: const BugReportDiagnostics(screen: 'chat'),
    );

    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('online submission succeeds and returns ticket and status', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '{"id":"rpt-1","ticket":"KARMI-0007","status":"new","created_at":"2026-11-07T10:00:00Z"}',
          201,
          headers: {'content-type': 'application/json'},
        );
      });

      final queue = BugReportQueue();
      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
      final service = BugReportService(api: api, queue: queue);

      final result = await service.submit(testRequest);
      expect(result.status, BugReportSubmissionStatus.submitted);
      expect(result.ticket, 'KARMI-0007');
      expect(result.reportStatus, 'new');

      // Should be removed from queue
      final pending = await queue.getPending();
      expect(pending.isEmpty, isTrue);
    });

    test('network failure enqueues report and returns queued status', () async {
      final mockClient = MockClient((request) async {
        throw http.ClientException('Network unreachable');
      });

      final queue = BugReportQueue();
      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
      final service = BugReportService(api: api, queue: queue);

      final result = await service.submit(testRequest);
      expect(result.status, BugReportSubmissionStatus.queued);
      expect(result.userMessage.contains('saved'), isTrue);

      // Pending queue contains the item
      final pending = await queue.getPending();
      expect(pending.length, 1);
      expect(pending.first.clientReportId, reportId);
    });

    test('429 rate limit sets retry-after and keeps in queue', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '{"detail":"rate limit"}',
          429,
          headers: {'retry-after': '7200'},
        );
      });

      final queue = BugReportQueue();
      final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
      final service = BugReportService(api: api, queue: queue);

      final result = await service.submit(testRequest);
      expect(result.status, BugReportSubmissionStatus.rateLimited);
      expect(result.userMessage.contains('2 hours'), isTrue);

      final pending = await queue.getPending();
      expect(pending.length, 1);
      expect(pending.first.isRateLimited, isTrue);
    });

    test(
      '413 payload too large marks rejected and drops from automatic retries',
      () async {
        final mockClient = MockClient((request) async {
          return http.Response('{"detail":"too large"}', 413);
        });

        final queue = BugReportQueue();
        final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
        final service = BugReportService(api: api, queue: queue);

        final result = await service.submit(testRequest);
        expect(result.status, BugReportSubmissionStatus.rejected);
        expect(
          result.userMessage,
          'That screenshot is too big. Turn off the screenshot or try again.',
        );

        // Not in pending retries
        final pending = await queue.getPending();
        expect(pending.isEmpty, isTrue);
      },
    );

    test(
      'flushQueue retries pending items and clears them upon success',
      () async {
        var callCount = 0;
        final mockClient = MockClient((request) async {
          callCount++;
          return http.Response(
            '{"id":"rpt-flush","ticket":"KARMI-0099","status":"new","created_at":"2026-11-07T10:00:00Z"}',
            201,
            headers: {'content-type': 'application/json'},
          );
        });

        final queue = BugReportQueue();
        await queue.enqueue(testRequest);

        final api = BugReportsApi(baseUrl: baseUrl, client: mockClient);
        final service = BugReportService(api: api, queue: queue);

        final sentCount = await service.flushQueue();
        expect(sentCount, 1);
        expect(callCount, 1);

        final pending = await queue.getPending();
        expect(pending.isEmpty, isTrue);
      },
    );
  });
}
