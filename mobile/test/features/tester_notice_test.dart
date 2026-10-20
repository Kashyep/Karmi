import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/app.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/welcome/tester_notice.dart';
import 'package:karmi_app/features/welcome/tester_notice_screen.dart';
import 'package:karmi_app/features/welcome/welcome_screen.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

void main() {
  testWidgets('first launch shows TesterNoticeScreen before app can be used', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({'dev_session_token': 'token'});
    final prefs = await SharedPreferences.getInstance();
    final settings = KarmiSettings(prefs);
    final backend = FakeBackend.healthy();
    final session = KarmiSession(
      api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
      prefs: prefs,
    );
    final armory = ArmoryController(
      api: session.api,
      prefs: prefs,
      appIcon: FakeAppIcons(),
    );
    addTearDown(armory.dispose);

    await tester.pumpWidget(
      KarmiApp(
        settings: settings,
        session: session,
        armory: armory,
        adaptiveGlassQuality: false,
      ),
    );
    await tester.pump();

    // TesterNoticeScreen is shown
    expect(find.byType(TesterNoticeScreen), findsOneWidget);
    expect(find.text(kTesterNoticeTitle), findsOneWidget);
    expect(find.text(kTesterNoticeText), findsOneWidget);
    expect(find.byType(KarmiShell), findsNothing);

    // Tap acknowledge button
    await tester.tap(find.text('I Understand and Acknowledge'));
    await tester.pumpAndSettle();

    // Now advances to KarmiShell and persists version
    expect(find.byType(TesterNoticeScreen), findsNothing);
    expect(find.byType(KarmiShell), findsOneWidget);
    expect(
      prefs.getInt('acknowledged_tester_notice_version'),
      kTesterNoticeVersion,
    );
  });

  testWidgets(
    'unacknowledged without session leads to WelcomeScreen after acknowledgment',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = KarmiSettings(prefs);
      final backend = FakeBackend.healthy();
      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        prefs: prefs,
      );
      final armory = ArmoryController(
        api: session.api,
        prefs: prefs,
        appIcon: FakeAppIcons(),
      );
      addTearDown(armory.dispose);

      await tester.pumpWidget(
        KarmiApp(
          settings: settings,
          session: session,
          armory: armory,
          adaptiveGlassQuality: false,
        ),
      );
      await tester.pump();

      expect(find.byType(TesterNoticeScreen), findsOneWidget);
      expect(find.byType(WelcomeScreen), findsNothing);

      await tester.tap(find.text('I Understand and Acknowledge'));
      await tester.pumpAndSettle();

      expect(find.byType(TesterNoticeScreen), findsNothing);
      expect(find.byType(WelcomeScreen), findsOneWidget);
    },
  );

  testWidgets(
    'bumping notice version re-prompts previously acknowledged users',
    (tester) async {
      // Acknowledged older version 0
      SharedPreferences.setMockInitialValues({
        'acknowledged_tester_notice_version': 0,
        'dev_session_token': 'token',
      });
      final prefs = await SharedPreferences.getInstance();
      final settings = KarmiSettings(prefs);
      expect(
        settings.isTesterNoticeAcknowledged(kTesterNoticeVersion),
        isFalse,
      );

      final backend = FakeBackend.healthy();
      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        prefs: prefs,
      );
      final armory = ArmoryController(
        api: session.api,
        prefs: prefs,
        appIcon: FakeAppIcons(),
      );
      addTearDown(armory.dispose);

      await tester.pumpWidget(
        KarmiApp(
          settings: settings,
          session: session,
          armory: armory,
          adaptiveGlassQuality: false,
        ),
      );
      await tester.pump();

      // Re-prompts because acknowledged version (0) < kTesterNoticeVersion (1)
      expect(find.byType(TesterNoticeScreen), findsOneWidget);
    },
  );
}
