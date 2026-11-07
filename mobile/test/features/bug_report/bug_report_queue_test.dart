import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/bug_reports/bug_report_models.dart';
import 'package:karmi_app/features/bug_report/bug_report_queue.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BugReportQueue offline persistence and idempotency replay', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test(
      'enqueues report and preserves exact payload and client_report_id',
      () async {
        final queue = BugReportQueue();
        const reportId = '550e8400-e29b-41d4-a716-446655440000';
        final request = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.chat,
          description: 'Something failed during message stream',
          diagnostics: const BugReportDiagnostics(
            appVersion: '1.0.0',
            screen: 'chat',
          ),
        );

        await queue.enqueue(request);

        final pending = await queue.getPending();
        expect(pending.length, 1);
        expect(pending.first.clientReportId, reportId);
        expect(pending.first.payload['client_report_id'], reportId);
        expect(pending.first.payload['category'], 'chat');
        expect(
          pending.first.payload['description'],
          'Something failed during message stream',
        );

        // Recreating request from payload results in identical payload
        final rehydrated = BugReportCreateRequest.fromJson(
          pending.first.payload,
        );
        expect(rehydrated.clientReportId, reportId);
        expect(rehydrated.category, BugReportCategory.chat);
        expect(
          rehydrated.description,
          'Something failed during message stream',
        );
      },
    );

    test(
      're-enqueuing with same client_report_id does not duplicate entry',
      () async {
        final queue = BugReportQueue();
        const reportId = '550e8400-e29b-41d4-a716-446655440000';
        final request = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.chat,
          description: 'Original text',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
        );

        await queue.enqueue(request);
        await queue.enqueue(request);

        final items = await queue.getAll();
        expect(items.length, 1);
      },
    );

    test(
      'rate limit sets retry_after_until timestamp and isRateLimited checks it',
      () async {
        final queue = BugReportQueue();
        const reportId = '550e8400-e29b-41d4-a716-446655440000';
        final request = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.ui,
          description: 'Button overflow occurred',
          diagnostics: const BugReportDiagnostics(screen: 'settings'),
        );

        await queue.enqueue(request);

        // Set rate limit for 60 seconds
        await queue.setRateLimit(reportId, 60);

        var pending = await queue.getPending();
        expect(pending.first.isRateLimited, isTrue);

        // Check remaining seconds is positive
        expect(pending.first.retryAfterRemainingSeconds, greaterThan(0));

        // With allowRateLimited = false, pending reports ready for immediate retry should be empty
        final ready = pending.where((i) => !i.isRateLimited).toList();
        expect(ready.isEmpty, isTrue);
      },
    );

    test(
      'markRejected marks item as rejected and drops from pending',
      () async {
        final queue = BugReportQueue();
        const reportId = '550e8400-e29b-41d4-a716-446655440000';
        final request = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.crash,
          description: 'App crashed when opening camera',
          diagnostics: const BugReportDiagnostics(screen: 'home'),
        );

        await queue.enqueue(request);
        await queue.markRejected(reportId, 'Payload too large');

        final pending = await queue.getPending();
        expect(pending.isEmpty, isTrue);

        final all = await queue.getAll();
        expect(all.length, 1);
        expect(all.first.isRejected, isTrue);
        expect(all.first.rejectionReason, 'Payload too large');
      },
    );

    test('remove deletes the item upon success (201 or 200 replay)', () async {
      final queue = BugReportQueue();
      const reportId = '550e8400-e29b-41d4-a716-446655440000';
      final request = BugReportCreateRequest(
        clientReportId: reportId,
        category: BugReportCategory.other,
        description: 'General feedback about font sizes',
        diagnostics: const BugReportDiagnostics(screen: 'profile'),
      );

      await queue.enqueue(request);
      expect((await queue.getAll()).length, 1);

      await queue.remove(reportId);
      expect((await queue.getAll()).isEmpty, isTrue);
    });
  });
}
