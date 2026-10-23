import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/app.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';
import 'package:karmi_app/features/welcome/tester_notice.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fake_admin_api.dart';
import '../../support/fake_backend.dart';
import '../../support/harness.dart';

Future<AdminController> _pump(
  WidgetTester tester,
  FakeAdminApi adminApi,
) async {
  tester.view
    ..physicalSize = kPhoneSize
    ..devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  SharedPreferences.setMockInitialValues({
    'dev_session_token': 'test-token',
    'acknowledged_tester_notice_version': kTesterNoticeVersion,
  });
  final prefs = await SharedPreferences.getInstance();
  final backend = FakeBackend.healthy();
  final settings = KarmiSettings(prefs);
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
  final admin = AdminController(api: adminApi);
  addTearDown(admin.dispose);

  await tester.pumpWidget(
    KarmiApp(
      settings: settings,
      session: session,
      armory: armory,
      admin: admin,
      adaptiveGlassQuality: false,
      clock: () => FakeBackend.pinnedNow,
    ),
  );
  await settle(tester);
  return admin;
}

void main() {
  testWidgets('non-admin account never sees the Admin console entry', (
    tester,
  ) async {
    await _pump(tester, FakeAdminApi(forbidden: true));
    await openTab(tester, 'Settings');
    await settle(tester);

    expect(find.byKey(const ValueKey('admin_console_tile')), findsNothing);
    expect(find.text('Admin console'), findsNothing);
  });

  testWidgets('eligible admin enters the admin shell only, then logs out', (
    tester,
  ) async {
    final admin = await _pump(tester, FakeAdminApi());
    await openTab(tester, 'Settings');
    await settle(tester);

    final tile = find.byKey(const ValueKey('admin_console_tile'));
    expect(tile, findsOneWidget);
    await tester.tap(tile);
    await settle(tester);

    await tester.enterText(
      find.byKey(const ValueKey('admin_code_field')),
      '123456',
    );
    await tester.tap(find.text('Continue'));
    await settle(tester);

    expect(find.byKey(const ValueKey('admin_shell')), findsOneWidget);
    expect(find.byType(KarmiShell), findsNothing);
    expect(find.text('Chat'), findsNothing);
    expect(find.text('Tasks'), findsNothing);
    expect(find.text('Usage'), findsNothing);
    expect(find.text('Settings'), findsNothing);

    await admin.logout();
    await settle(tester);

    expect(find.byKey(const ValueKey('admin_shell')), findsNothing);
    expect(find.byType(KarmiShell), findsOneWidget);
    admin.reset();
  });
}
