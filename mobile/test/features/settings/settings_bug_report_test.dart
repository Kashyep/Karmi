import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/bug_report/bug_report_screen.dart';
import 'package:karmi_app/features/settings/settings_screen.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets(
    'SettingsScreen has Report a bug entry that opens BugReportScreen',
    (tester) async {
      final prefs = await SharedPreferences.getInstance();
      final api = KarmiApi(baseUrl: 'http://test');
      final settings = KarmiSettings(prefs);
      final session = KarmiSession(api: api, prefs: prefs);
      final armory = ArmoryController(api: api, prefs: prefs);

      await tester.pumpWidget(
        MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
          home: Scaffold(
            body: SettingsScreen(
              settings: settings,
              session: session,
              armory: armory,
              onOpenArmory: () {},
            ),
          ),
        ),
      );

      // Verify tile is present
      final tileFinder = find.byKey(const ValueKey('report_bug_tile'));
      expect(tileFinder, findsOneWidget);
      expect(find.text('Report a bug'), findsOneWidget);
      expect(find.text('Send diagnostics or report an issue'), findsOneWidget);

      // Tap tile opens BugReportScreen
      await tester.tap(tileFinder);
      await tester.pumpAndSettle();

      expect(find.byType(BugReportScreen), findsOneWidget);
      final BugReportScreen screen = tester.widget(
        find.byType(BugReportScreen),
      );
      expect(screen.initialScreen, 'settings');
    },
  );

  testWidgets('SettingsScreen default onOpenBugReport pushes BugReportScreen', (
    tester,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final api = KarmiApi(baseUrl: 'http://test');
    final settings = KarmiSettings(prefs);
    final session = KarmiSession(api: api, prefs: prefs);
    final armory = ArmoryController(api: api, prefs: prefs);
    await tester.pumpWidget(
      MaterialApp(
        theme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
        home: Scaffold(
          body: SettingsScreen(
            settings: settings,
            session: session,
            armory: armory,
            onOpenArmory: () {},
          ),
        ),
      ),
    );

    final tileFinder = find.byKey(const ValueKey('report_bug_tile'));
    await tester.tap(tileFinder);
    await tester.pumpAndSettle();

    expect(find.byType(BugReportScreen), findsOneWidget);
  });
}
