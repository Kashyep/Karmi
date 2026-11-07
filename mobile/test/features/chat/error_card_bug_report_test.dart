import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/features/bug_report/bug_report_screen.dart';
import 'package:karmi_app/features/chat/error_card.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets(
    'ErrorCard renders accessible Report this control and navigates when tapped',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
          home: Scaffold(
            body: ErrorCard(category: ErrorCategory.network, onRetry: () {}),
          ),
        ),
      );

      final linkFinder = find.byKey(const ValueKey('error_card_report_link'));
      expect(linkFinder, findsOneWidget);
      expect(find.text('Report this'), findsOneWidget);

      // Minimum 48 dp tap target
      final size = tester.getSize(linkFinder);
      expect(size.width, greaterThanOrEqualTo(48.0));
      expect(size.height, greaterThanOrEqualTo(48.0));

      // Accessible semantics
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is Semantics &&
              w.properties.button == true &&
              w.properties.label == 'Report this problem',
        ),
        findsOneWidget,
      );

      await tester.tap(linkFinder);
      await tester.pumpAndSettle();

      expect(find.byType(BugReportScreen), findsOneWidget);
    },
  );

  testWidgets(
    'ErrorCard default Report this navigates to prefilled BugReportScreen',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
          home: const Scaffold(
            body: ErrorCard(
              category: ErrorCategory.timeout,
              errorCode: 'SSE_TIMEOUT',
            ),
          ),
        ),
      );

      final linkFinder = find.byKey(const ValueKey('error_card_report_link'));
      await tester.tap(linkFinder);
      await tester.pumpAndSettle();

      final screenFinder = find.byType(BugReportScreen);
      expect(screenFinder, findsOneWidget);

      final BugReportScreen screen = tester.widget(screenFinder);
      expect(screen.initialScreen, 'chat');
      expect(screen.initialErrorCode, 'SSE_TIMEOUT');
    },
  );

  testWidgets(
    'ErrorCard passes session and userId through to BugReportScreen',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
          home: const Scaffold(
            body: ErrorCard(
              category: ErrorCategory.timeout,
              errorCode: 'SSE_TIMEOUT',
              userId: 'user_456',
            ),
          ),
        ),
      );

      final linkFinder = find.byKey(const ValueKey('error_card_report_link'));
      await tester.tap(linkFinder);
      await tester.pumpAndSettle();

      final screenFinder = find.byType(BugReportScreen);
      expect(screenFinder, findsOneWidget);

      final BugReportScreen screen = tester.widget(screenFinder);
      expect(screen.userId, 'user_456');
    },
  );
}
