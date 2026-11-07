import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/bug_reports/bug_report_models.dart';
import 'package:karmi_app/api/bug_reports/bug_reports_api.dart';
import 'package:karmi_app/features/bug_report/bug_report_queue.dart';
import 'package:karmi_app/features/bug_report/bug_report_screen.dart';
import 'package:karmi_app/features/bug_report/bug_report_service.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:shared_preferences/shared_preferences.dart';

class MockBugReportService extends BugReportService {
  MockBugReportService({required this.onSubmitting, BugReportQueue? queue})
    : super(
        api: BugReportsApi(baseUrl: 'https://test'),
        queue: queue ?? BugReportQueue(),
      );

  final Future<BugReportSubmissionResult> Function(
    BugReportCreateRequest request,
  )
  onSubmitting;
  BugReportCreateRequest? lastSubmittedRequest;

  @override
  Future<BugReportSubmissionResult> submit(
    BugReportCreateRequest request,
  ) async {
    lastSubmittedRequest = request;
    return onSubmitting(request);
  }
}

Widget createTestableWidget({
  required Widget child,
  Brightness brightness = Brightness.dark,
}) {
  return MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, brightness),
    home: Scaffold(body: child),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('BugReportScreen Widget Tests', () {
    testWidgets('shows category picker with plain words', (tester) async {
      await tester.pumpWidget(
        createTestableWidget(child: const BugReportScreen()),
      );

      expect(find.text('Report a bug'), findsOneWidget);
      expect(find.text('Category'), findsOneWidget);
      expect(find.text('Chat or assistant'), findsOneWidget);
    });

    testWidgets(
      'description boundaries: 9 chars blocks submit, 10 allows submit',
      (tester) async {
        var submitted = false;
        final mockService = MockBugReportService(
          onSubmitting: (req) async {
            submitted = true;
            return const BugReportSubmissionResult.submitted(
              ticket: 'KARMI-0042',
              reportStatus: 'new',
            );
          },
        );

        await tester.pumpWidget(
          createTestableWidget(child: BugReportScreen(service: mockService)),
        );

        final sendButtonFinder = find.widgetWithText(
          FilledButton,
          'Send bug report',
        );
        expect(sendButtonFinder, findsOneWidget);

        // Initially empty -> send button disabled
        final FilledButton initialButton = tester.widget(sendButtonFinder);
        expect(initialButton.onPressed, isNull);

        // 9 chars -> still disabled
        await tester.enterText(
          find.byKey(const ValueKey('description-field')),
          '123456789',
        );
        await tester.pump();

        expect(find.text('9 / 2000'), findsOneWidget);
        expect(
          find.text('Please provide at least 10 characters'),
          findsOneWidget,
        );
        final FilledButton button9 = tester.widget(sendButtonFinder);
        expect(button9.onPressed, isNull);

        // 10 chars -> enabled
        await tester.enterText(
          find.byKey(const ValueKey('description-field')),
          '1234567890',
        );
        await tester.pump();

        expect(find.text('10 / 2000'), findsOneWidget);
        expect(
          find.text('Please provide at least 10 characters'),
          findsNothing,
        );
        final FilledButton button10 = tester.widget(sendButtonFinder);
        expect(button10.onPressed, isNotNull);

        await tester.tap(sendButtonFinder);
        await tester.pumpAndSettle();

        expect(submitted, isTrue);
        expect(find.text('Ticket: KARMI-0042'), findsOneWidget);
        expect(find.text('Status: new'), findsOneWidget);
      },
    );

    testWidgets(
      'description boundaries: 2000 chars allows submit, 2001 blocks submit',
      (tester) async {
        final mockService = MockBugReportService(
          onSubmitting: (req) async =>
              const BugReportSubmissionResult.submitted(ticket: 'KARMI-0001'),
        );

        await tester.pumpWidget(
          createTestableWidget(child: BugReportScreen(service: mockService)),
        );

        final sendButtonFinder = find.widgetWithText(
          FilledButton,
          'Send bug report',
        );

        // 2000 chars -> enabled
        final text2000 = 'a' * 2000;
        await tester.enterText(
          find.byKey(const ValueKey('description-field')),
          text2000,
        );
        await tester.pump();

        expect(find.text('2000 / 2000'), findsOneWidget);
        final FilledButton button2000 = tester.widget(sendButtonFinder);
        expect(button2000.onPressed, isNotNull);

        // 2001 chars -> blocked
        final text2001 = 'a' * 2001;
        await tester.enterText(
          find.byKey(const ValueKey('description-field')),
          text2001,
        );
        await tester.pump();

        expect(find.text('2001 / 2000'), findsOneWidget);
        expect(
          find.text('Description exceeds 2000 characters limit'),
          findsOneWidget,
        );
        final FilledButton button2001 = tester.widget(sendButtonFinder);
        expect(button2001.onPressed, isNull);
      },
    );

    testWidgets(
      'screenshot toggle is OFF by default and shows notice when toggled ON',
      (tester) async {
        await tester.pumpWidget(
          createTestableWidget(child: const BugReportScreen()),
        );

        final toggleFinder = find.byKey(
          const ValueKey('screenshot-consent-toggle'),
        );
        expect(toggleFinder, findsOneWidget);

        final Switch toggle = tester.widget(toggleFinder);
        expect(toggle.value, isFalse);
        expect(find.byKey(const ValueKey('screenshot-notice')), findsNothing);

        // Toggle ON
        await tester.tap(toggleFinder);
        await tester.pump();

        expect(find.byKey(const ValueKey('screenshot-notice')), findsOneWidget);
        expect(
          find.text(
            'Notice: The screenshot may include on-screen content. Please ensure no sensitive information is shown.',
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'screenshot larger than 5 MB displays error and blocks invalid upload',
      (tester) async {
        // 5.5 MB bytes
        final largeBytes = Uint8List(5 * 1024 * 1024 + 500 * 1024);

        await tester.pumpWidget(
          createTestableWidget(
            child: BugReportScreen(initialScreenshotBytes: largeBytes),
          ),
        );

        final toggleFinder = find.byKey(
          const ValueKey('screenshot-consent-toggle'),
        );
        await tester.tap(toggleFinder);
        await tester.pump();

        expect(
          find.byKey(const ValueKey('screenshot-error-message')),
          findsOneWidget,
        );
        expect(
          find.text(
            'That screenshot is too big. Turn off the screenshot or try again.',
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'diagnostics preview table expands and shows allowlist values',
      (tester) async {
        await tester.pumpWidget(
          createTestableWidget(
            child: const BugReportScreen(
              initialScreen: 'chat',
              initialErrorCode: 'TIMEOUT_ERR',
            ),
          ),
        );

        // Initially collapsed
        expect(find.byKey(const ValueKey('diagnostics-table')), findsNothing);

        // Tap header to expand
        await tester.tap(find.textContaining('Diagnostics to be sent'));
        await tester.pump();

        expect(find.byKey(const ValueKey('diagnostics-table')), findsOneWidget);
        expect(find.text('screen'), findsOneWidget);
        expect(find.text('chat'), findsOneWidget);
        expect(find.text('error_code'), findsOneWidget);
        expect(find.text('TIMEOUT_ERR'), findsOneWidget);
      },
    );
  });
}
