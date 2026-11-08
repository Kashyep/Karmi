import 'dart:convert';
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

        await queue.enqueue(request, userId: 'user_test');

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

        await queue.enqueue(request, userId: 'user_test');
        await queue.enqueue(request, userId: 'user_test');

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

        await queue.enqueue(request1, userId: 'user_test');
        var items = await queue.getAll();
        expect(items.length, 1);
        expect(items.first.payload['description'], 'Original text');

        await queue.enqueue(request2, userId: 'user_test');
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
            contentType: 'image/png',
            dataBase64:
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
          ),
        );

        await queue.enqueue(request1, userId: 'user_test');
        final item1 = (await queue.getAll()).first;

        await Future<void>.delayed(const Duration(milliseconds: 10));
        await queue.enqueue(request2, userId: 'user_test');
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

        await queue.enqueue(request, userId: 'user_test');

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

        await queue.enqueue(request, userId: 'user_test');
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

      await queue.enqueue(request, userId: 'user_test');
      expect((await queue.getAll()).length, 1);

      await queue.remove(reportId);
      expect((await queue.getAll()).isEmpty, isTrue);
    });
    test('enqueue without an owner throws ArgumentError', () async {
      final queue = BugReportQueue();
      const reportId = '550e8400-e29b-41d4-a716-446655440000';
      final request = BugReportCreateRequest(
        clientReportId: reportId,
        category: BugReportCategory.chat,
        description: 'Test report',
        diagnostics: const BugReportDiagnostics(screen: 'chat'),
      );
      expect(() => queue.enqueue(request), throwsArgumentError);
      expect(() => queue.enqueue(request, userId: ''), throwsArgumentError);
    });

    test(
      'clearUserItems removes only the specified user items and screenshots',
      () async {
        final queue = BugReportQueue();
        final req1 = BugReportCreateRequest(
          clientReportId: '550e8400-e29b-41d4-a716-446655440010',
          category: BugReportCategory.chat,
          description: 'User 1 feedback',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
        );
        final req2 = BugReportCreateRequest(
          clientReportId: '550e8400-e29b-41d4-a716-446655440020',
          category: BugReportCategory.chat,
          description: 'User 2 feedback',
          diagnostics: const BugReportDiagnostics(screen: 'chat'),
        );

        await queue.enqueue(req1, userId: 'user_1');
        await queue.enqueue(req2, userId: 'user_2');

        expect((await queue.getAll()).length, 2);

        await queue.clearUserItems('user_1');

        final remaining = await queue.getAll();
        expect(remaining.length, 1);
        expect(remaining.first.userId, 'user_2');
      },
    );

    test('legacy rejected item is dropped on load and unpersisted', () async {
      final prefs = await SharedPreferences.getInstance();
      final legacyRejectedJson = jsonEncode({
        'client_report_id': 'legacy-rejected-001',
        'payload': {
          'client_report_id': 'legacy-rejected-001',
          'category': 'chat',
          'description': 'Rejected error report',
        },
        'created_at': DateTime.now().toUtc().toIso8601String(),
        'user_id': 'user_legacy',
        'is_rejected': true,
        'rejection_reason': 'Server rejected 422',
      });
      final validJson = jsonEncode({
        'client_report_id': 'valid-item-001',
        'payload': {
          'client_report_id': 'valid-item-001',
          'category': 'chat',
          'description': 'Valid report',
        },
        'created_at': DateTime.now().toUtc().toIso8601String(),
        'user_id': 'user_legacy',
      });
      await prefs.setStringList(BugReportQueue.prefKey, [
        legacyRejectedJson,
        validJson,
      ]);

      final queue = BugReportQueue();
      final items = await queue.loadAll();

      expect(items.length, 1);
      expect(items.first.clientReportId, 'valid-item-001');

      // Idempotency: verify prefs list was cleaned in place
      final persisted = prefs.getStringList(BugReportQueue.prefKey)!;
      expect(persisted.length, 1);
      expect(persisted.first.contains('legacy-rejected-001'), isFalse);
    });

    test(
      'legacy ownerless item is dropped on load and its screenshot unpersisted',
      () async {
        final prefs = await SharedPreferences.getInstance();
        final scKey = BugReportQueue.screenshotPrefKey('legacy-ownerless-001');
        await prefs.setString(
          scKey,
          '{"content_type":"image/png","data_base64":"abc"}',
        );

        final legacyOwnerlessJson = jsonEncode({
          'client_report_id': 'legacy-ownerless-001',
          'payload': {
            'client_report_id': 'legacy-ownerless-001',
            'category': 'chat',
            'description': 'Ownerless report',
          },
          'created_at': DateTime.now().toUtc().toIso8601String(),
        });
        final validJson = jsonEncode({
          'client_report_id': 'valid-item-002',
          'payload': {
            'client_report_id': 'valid-item-002',
            'category': 'chat',
            'description': 'Valid report with owner',
          },
          'created_at': DateTime.now().toUtc().toIso8601String(),
          'user_id': 'user_owner',
        });
        await prefs.setStringList(BugReportQueue.prefKey, [
          legacyOwnerlessJson,
          validJson,
        ]);

        final queue = BugReportQueue();
        final items = await queue.loadAll();

        expect(items.length, 1);
        expect(items.first.clientReportId, 'valid-item-002');
        expect(prefs.containsKey(scKey), isFalse);

        final persisted = prefs.getStringList(BugReportQueue.prefKey)!;
        expect(persisted.length, 1);
        expect(persisted.first.contains('legacy-ownerless-001'), isFalse);
      },
    );

    test(
      'legacy inline screenshot is migrated to separate storage and stripped from queue entry',
      () async {
        final prefs = await SharedPreferences.getInstance();
        const screenshotData = {
          'content_type': 'image/png',
          'data_base64':
              'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
        };
        final legacyInlineJson = jsonEncode({
          'client_report_id': 'legacy-inline-001',
          'payload': {
            'client_report_id': 'legacy-inline-001',
            'category': 'chat',
            'description': 'Report with inline screenshot',
            'diagnostics': {'screen': 'chat'},
            'screenshot': screenshotData,
          },
          'created_at': DateTime.now().toUtc().toIso8601String(),
          'user_id': 'user_owner',
        });
        await prefs.setStringList(BugReportQueue.prefKey, [legacyInlineJson]);

        final queue = BugReportQueue();
        final items = await queue.loadAll();
        expect(items.length, 1);
        expect(items.first.payload.containsKey('screenshot'), isFalse);

        // Stored separately in keyed screenshot storage
        final scKey = BugReportQueue.screenshotPrefKey('legacy-inline-001');
        expect(prefs.containsKey(scKey), isTrue);

        // Resolves properly with screenshot restored
        final resolved = await queue.resolveRequest(items.first);
        expect(resolved.screenshot, isNotNull);
        expect(resolved.screenshot!.contentType, 'image/png');
        expect(resolved.screenshot!.dataBase64, isNotEmpty);
        // Persisted queue entry no longer has inline screenshot
        final persisted = prefs.getStringList(BugReportQueue.prefKey)!;
        final decoded = jsonDecode(persisted.first) as Map<String, dynamic>;
        expect((decoded['payload'] as Map).containsKey('screenshot'), isFalse);
      },
    );
  });
}
