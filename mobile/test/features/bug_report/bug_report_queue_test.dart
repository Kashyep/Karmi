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
      're-enqueuing with same client_report_id replaces queued item when payload changes',
      () async {
        final queue = BugReportQueue();
        const reportId = '550e8400-e29b-41d4-a716-446655440000';
        final request1 = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.chat,
          description: 'Original text',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
        );
        final request2 = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.chat,
          description: 'Updated text after retry',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
        );

        await queue.enqueue(request1);
        var items = await queue.getAll();
        expect(items.length, 1);
        expect(items.first.payload['description'], 'Original text');

        await queue.enqueue(request2);
        items = await queue.getAll();
        expect(items.length, 1);
        expect(items.first.payload['description'], 'Updated text after retry');
      },
    );

    test(
      're-enqueuing with same client_report_id replaces queued item when screenshot changes',
      () async {
        final queue = BugReportQueue();
        const reportId = '550e8400-e29b-41d4-a716-446655440000';
        final request1 = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.chat,
          description: 'Original text',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
        );
        final request2 = BugReportCreateRequest(
          clientReportId: reportId,
          category: BugReportCategory.chat,
          description: 'Original text',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
          screenshot: const BugReportScreenshot(
            bytesBase64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
            width: 1,
            height: 1,
          ),
        );

        await queue.enqueue(request1);
        final item1 = (await queue.getAll()).first;

        await Future<void>.delayed(const Duration(milliseconds: 10));
        await queue.enqueue(request2);
        final item2 = (await queue.getAll()).first;

        expect(item2.createdAt.isAfter(item1.createdAt), isTrue);
        final resolved = await queue.resolveRequest(item2);
        expect(resolved.screenshot, isNotNull);
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
      'markRejected drops rejected item so it is not retained in storage',
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
        expect(all.isEmpty, isTrue);
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

    test('clearUserItems removes only the specified user items and screenshots', () async {
      final queue = BugReportQueue();
      const req1 = BugReportCreateRequest(
        clientReportId: '550e8400-e29b-41d4-a716-446655440010',
        category: BugReportCategory.chat,
        description: 'User 1 feedback',
        diagnostics: BugReportDiagnostics(screen: 'chat'),
      );
      const req2 = BugReportCreateRequest(
        clientReportId: '550e8400-e29b-41d4-a716-446655440020',
        category: BugReportCategory.chat,
        description: 'User 2 feedback',
        diagnostics: BugReportDiagnostics(screen: 'chat'),
      );

      await queue.enqueue(req1, userId: 'user_1');
      await queue.enqueue(req2, userId: 'user_2');

      expect((await queue.getAll()).length, 2);

      await queue.clearUserItems('user_1');

      final remaining = await queue.getAll();
      expect(remaining.length, 1);
      expect(remaining.first.userId, 'user_2');
    });
  });
}
