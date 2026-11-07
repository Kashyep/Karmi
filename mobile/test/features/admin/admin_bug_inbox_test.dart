import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';
import 'package:karmi_app/features/admin/bug_inbox_screen.dart';
import 'package:karmi_app/features/admin/bug_report_detail_screen.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

import '../../support/fake_admin_api.dart';

AdminBugReportDetail _sampleReport({
  String id = 'b1',
  String ticket = 'KARMI-0042',
  String category = 'chat',
  String status = 'new',
  String description = 'App froze during chat streaming',
  Map<String, dynamic>? diagnostics,
  String? adminNotes,
  bool hasScreenshot = false,
  DateTime? triagedAt,
  DateTime? resolvedAt,
}) => AdminBugReportDetail(
  id: id,
  ticket: ticket,
  category: category,
  description: description,
  diagnostics:
      diagnostics ??
      const {
        'app_version': '0.1.0',
        'os': 'android',
        'device_model': 'Pixel 9a',
      },
  status: status,
  adminNotes: adminNotes,
  hasScreenshot: hasScreenshot,
  user: const AdminBugReportUser(
    id: 'u1',
    displayName: 'Alice Tester',
    plan: 'ananta',
  ),
  createdAt: DateTime.utc(2026, 3, 1, 10),
  updatedAt: DateTime.utc(2026, 3, 1, 11),
  triagedAt: triagedAt,
  resolvedAt: resolvedAt,
);

final List<AdminController> _live = [];

void adminTest(
  String description,
  Future<void> Function(WidgetTester tester) body,
) {
  testWidgets(description, (tester) async {
    _live.clear();
    await body(tester);
    await tester.pump(const Duration(minutes: 16));
    await tester.pumpWidget(const SizedBox());
    for (final c in _live) {
      c.dispose();
    }
  });
}

Future<AdminController> signedIn(FakeAdminApi api) async {
  final controller = AdminController(api: api);
  _live.add(controller);
  await controller.verifyCode(api.code);
  return controller;
}

Future<void> _pumpScreen(WidgetTester tester, {required Widget child}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(body: child),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('transition table legal targets verification', () {
    for (final state in kAllowedBugReportStatuses) {
      test('state "$state" transitions match backend invariant exactly', () {
        final allowed = kAllowedBugReportTransitions[state];
        expect(allowed, isNotNull, reason: 'Every status must be in the map');
        expect(allowed, isNotEmpty, reason: 'Every status has legal targets');

        switch (state) {
          case 'new':
            expect(
              allowed,
              equals({'triaged', 'duplicate', 'wontfix', 'closed'}),
            );
          case 'triaged':
            expect(
              allowed,
              equals({'in_progress', 'duplicate', 'wontfix', 'closed'}),
            );
          case 'in_progress':
            expect(allowed, equals({'fixed', 'wontfix', 'closed'}));
          case 'fixed':
            expect(allowed, equals({'closed', 'in_progress'}));
          case 'duplicate':
            expect(allowed, equals({'closed', 'triaged'}));
          case 'wontfix':
            expect(allowed, equals({'closed', 'triaged'}));
          case 'closed':
            expect(allowed, equals({'triaged'}));
          default:
            fail('Unexpected status $state');
        }
      });
    }

    for (final state in kAllowedBugReportStatuses) {
      adminTest('transition picker only shows legal targets for "$state"', (
        tester,
      ) async {
        final report = _sampleReport(id: 'rep-$state', status: state);
        final api = FakeAdminApi(bugReports: [report]);
        final controller = await signedIn(api);

        await _pumpScreen(
          tester,
          child: BugReportDetailScreen(
            controller: controller,
            reportId: report.id,
          ),
        );

        final updateBtn = find.widgetWithText(FilledButton, 'Update status');
        expect(updateBtn, findsOneWidget);
        await tester.tap(updateBtn);
        await tester.pumpAndSettle();

        // Inspect dropdown options inside the dialog
        final dropdown = tester.widget<DropdownButton<String>>(
          find.byType(DropdownButton<String>),
        );
        final optionValues = dropdown.items!.map((item) => item.value).toSet();
        final expectedAllowed = kAllowedBugReportTransitions[state]!;
        expect(
          optionValues,
          equals(expectedAllowed),
          reason: 'Picker for $state must show strictly its legal targets',
        );

        // Close dialog
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
      });
    }
  });

  group('detail screen rendering', () {
    adminTest(
      'renders all report fields, user summary, diagnostics and timestamps',
      (tester) async {
        final report = _sampleReport(
          ticket: 'KARMI-9999',
          category: 'chat',
          status: 'new',
          description: 'Detailed bug explanation for chat stream failure',
          adminNotes: 'Prior note on bug',
          hasScreenshot: true,
        );
        final api = FakeAdminApi(bugReports: [report]);
        final controller = await signedIn(api);

        await _pumpScreen(
          tester,
          child: BugReportDetailScreen(
            controller: controller,
            reportId: report.id,
          ),
        );

        expect(find.text('KARMI-9999'), findsWidgets);
        expect(find.text('Category: Chat'), findsOneWidget);
        expect(find.text('New'), findsOneWidget);
        expect(
          find.text('Detailed bug explanation for chat stream failure'),
          findsOneWidget,
        );
        expect(find.text('Prior note on bug'), findsOneWidget);

        // User summary
        expect(find.text('Alice Tester'), findsOneWidget);
        expect(find.text('u1'), findsOneWidget);
        expect(find.text('Ananta'), findsOneWidget);

        // Diagnostics table
        expect(find.text('app_version'), findsOneWidget);
        expect(find.text('0.1.0'), findsOneWidget);
        expect(find.text('device_model'), findsOneWidget);
        expect(find.text('Pixel 9a'), findsOneWidget);

        // Screenshot button is visible
        expect(find.text('View screenshot'), findsOneWidget);
      },
    );
  });

  group('mutations & PATCH body', () {
    adminTest('status update sends reason and only changed fields', (
      tester,
    ) async {
      final report = _sampleReport(
        id: 'b1',
        status: 'new',
        adminNotes: 'Original note',
      );
      final api = FakeAdminApi(bugReports: [report]);
      final controller = await signedIn(api);

      await _pumpScreen(
        tester,
        child: BugReportDetailScreen(
          controller: controller,
          reportId: report.id,
        ),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'Update status'));
      await tester.pumpAndSettle();

      // Enter required reason
      await tester.enterText(
        find.widgetWithText(TextField, 'Reason (required)'),
        'triaged by admin',
      );
      await tester.pump();

      // Confirm button
      await tester.tap(find.widgetWithText(FilledButton, 'Update'));
      await tester.pumpAndSettle();

      // Verify FakeAdminApi recorded call with status changed and original notes unchanged
      // In FakeAdminApi: patchBugReport:b1:status=triaged:adminNotes=:triaged by admin
      expect(
        api.calls.any(
          (c) =>
              c.startsWith('patchBugReport:b1:status=triaged:') &&
              c.contains('triaged by admin'),
        ),
        isTrue,
      );
    });

    adminTest('409 conflict displays plain words error', (tester) async {
      final report = _sampleReport(id: 'b1', status: 'new');
      final api = FakeAdminApi(bugReports: [report]);
      final controller = await signedIn(api);

      await _pumpScreen(
        tester,
        child: BugReportDetailScreen(
          controller: controller,
          reportId: report.id,
        ),
      );

      // Force next call (the PATCH call) to fail with 409 conflict
      api.failNext = const AdminFailure(409);

      await tester.tap(find.widgetWithText(FilledButton, 'Update status'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'Reason (required)'),
        'triage conflicting',
      );
      await tester.pump();

      await tester.tap(find.widgetWithText(FilledButton, 'Update'));
      await tester.pumpAndSettle();

      // Expect plain words error
      expect(
        find.text(
          'This update conflicts with the current status. Refresh and try again.',
        ),
        findsOneWidget,
      );
    });
  });

  group('screenshot viewing via authenticated fetch', () {
    adminTest(
      'fetches bytes via authenticated client and displays Image.memory',
      (tester) async {
        final report = _sampleReport(id: 'b-img', hasScreenshot: true);
        // Valid minimal PNG bytes
        final pngBytes = Uint8List.fromList([
          0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, // signature
          0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, // IHDR
          0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
          0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
          0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
          0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
          0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
          0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
          0x42, 0x60, 0x82,
        ]);
        final api = FakeAdminApi(bugReports: [report]);
        api.bugReportScreenshots['b-img'] = pngBytes;
        final controller = await signedIn(api);

        await _pumpScreen(
          tester,
          child: BugReportDetailScreen(
            controller: controller,
            reportId: report.id,
          ),
        );

        final viewBtn = find.widgetWithText(FilledButton, 'View screenshot');
        expect(viewBtn, findsOneWidget);
        await tester.tap(viewBtn);
        await tester.pumpAndSettle();

        // Verify that api.getBugReportScreenshot was called (recorded)
        expect(api.calls, contains('getBugReportScreenshot:b-img'));

        // Verify Image widget is displayed from memory (not NetworkImage)
        final imgFinder = find.byType(Image);
        expect(imgFinder, findsOneWidget);
        final imageWidget = tester.widget<Image>(imgFinder);
        expect(imageWidget.image, isA<MemoryImage>());

        // Close dialog
        await tester.tap(find.text('Close'));
        await tester.pumpAndSettle();
      },
    );

    adminTest('screenshot 404 displays plain message', (tester) async {
      final report = _sampleReport(id: 'b-no-img', hasScreenshot: true);
      final api = FakeAdminApi(bugReports: [report]);
      // No screenshot added in api.bugReportScreenshots -> throws 404
      final controller = await signedIn(api);

      await _pumpScreen(
        tester,
        child: BugReportDetailScreen(
          controller: controller,
          reportId: report.id,
        ),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'View screenshot'));
      await tester.pumpAndSettle();

      expect(find.text('The requested item was not found.'), findsOneWidget);
    });
  });

  group('inbox list filters and pagination', () {
    adminTest('filters trigger query parameters reload', (tester) async {
      final reports = [
        _sampleReport(
          id: 'b1',
          ticket: 'KARMI-0001',
          category: 'crash',
          status: 'new',
        ),
        _sampleReport(
          id: 'b2',
          ticket: 'KARMI-0002',
          category: 'chat',
          status: 'triaged',
        ),
      ];
      final api = FakeAdminApi(bugReports: reports);
      final controller = await signedIn(api);

      await _pumpScreen(tester, child: BugInboxScreen(controller: controller));

      expect(find.text('KARMI-0001'), findsOneWidget);
      expect(find.text('KARMI-0002'), findsOneWidget);

      // Select 'Crash' category filter chip
      await tester.tap(find.widgetWithText(FilterChip, 'Crash'));
      await tester.pumpAndSettle();

      expect(api.calls.any((c) => c.contains('category=crash')), isTrue);
      expect(find.text('KARMI-0001'), findsOneWidget);
      expect(find.text('KARMI-0002'), findsNothing);

      // Select 'Triaged' status filter chip
      await tester.tap(find.widgetWithText(FilterChip, 'Triaged'));
      await tester.pumpAndSettle();

      expect(api.calls.any((c) => c.contains('status=triaged')), isTrue);
    });

    adminTest('cursor pagination loads next page with next_cursor', (
      tester,
    ) async {
      final reports = List.generate(
        4,
        (i) => _sampleReport(
          id: 'b-$i',
          ticket: 'KARMI-${(i + 1).toString().padLeft(4, '0')}',
        ),
      );
      final api = FakeAdminApi(bugReports: reports)..pageSize = 2;
      final controller = await signedIn(api);

      await _pumpScreen(tester, child: BugInboxScreen(controller: controller));

      // Initial page loads first 2
      expect(find.text('KARMI-0001'), findsOneWidget);
      expect(find.text('KARMI-0002'), findsOneWidget);
      expect(find.text('KARMI-0003'), findsNothing);

      // Tap 'Load more reports'
      final loadMore = find.widgetWithText(OutlinedButton, 'Load more reports');
      expect(loadMore, findsOneWidget);
      await tester.tap(loadMore);
      await tester.pumpAndSettle();

      // Verify cursor was passed
      expect(api.calls.any((c) => c.contains('cursor=2')), isTrue);
      expect(find.text('KARMI-0003'), findsOneWidget);
    });
  });
}
