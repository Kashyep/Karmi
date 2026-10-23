@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_action_dialog.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';
import 'package:karmi_app/features/admin/admin_shell.dart';
import 'package:karmi_app/features/admin/audit_screen.dart';
import 'package:karmi_app/features/admin/monitor_screen.dart';
import 'package:karmi_app/features/admin/user_detail_screen.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

import 'support/fake_admin_api.dart';
import 'support/harness.dart';

/// Goldens are stored per host OS; see [goldenPath].
String _golden(String name) => goldenPath('admin_$name');

DateTime _fixedClock() => DateTime.utc(2026, 3, 4, 12, 30);

Future<AdminController> _signedIn(FakeAdminApi api) async {
  final controller = AdminController(api: api);
  await controller.verifyCode(api.code);
  return controller;
}

Future<void> _end(WidgetTester tester, AdminController controller) async {
  await tester.pumpWidget(const SizedBox());
  controller.dispose();
}

Future<void> _pump(
  WidgetTester tester, {
  required Widget home,
  Size size = kPhoneSize,
  Brightness brightness = Brightness.light,
  double textScale = 1.0,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      darkTheme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
      themeMode: brightness == Brightness.dark ? ThemeMode.dark : ThemeMode.light,
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: TextScaler.linear(textScale),
        ),
        child: child!,
      ),
      home: home,
    ),
  );
  await settle(tester);
}

class _AuditFake extends FakeAdminApi {
  @override
  Future<AuditPage> audit(String token, {int limit = 50, String? cursor}) async {
    return AuditPage(
      items: [
        AuditEntry(
          id: 'a1',
          action: 'suspend',
          at: DateTime.utc(2026, 3, 4, 10),
          adminUserId: 'admin',
          targetUserId: 'u1',
          reason: 'abuse report',
        ),
        AuditEntry(
          id: 'a2',
          action: 'set_tier',
          at: DateTime.utc(2026, 3, 3, 9),
          adminUserId: 'admin',
          targetUserId: 'u2',
          reason: 'upgrade request',
        ),
      ],
    );
  }
}

void main() {
  for (final brightness in Brightness.values) {
    final name = brightness.name;
    testWidgets('users narrow $name', (tester) async {
      final controller = await _signedIn(FakeAdminApi());
        await _pump(
        tester,
        home: AdminShell(controller: controller),
        brightness: brightness,
      );
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(_golden('users_narrow_$name')),
      );
      await _end(tester, controller);
    }, tags: ['golden']);
  }

  testWidgets('users wide light', (tester) async {
    final controller = await _signedIn(FakeAdminApi());
    await _pump(
      tester,
      home: AdminShell(controller: controller),
      size: const Size(1280, 800),
    );
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(_golden('users_wide_light')),
    );
    await _end(tester, controller);
  }, tags: ['golden']);

  testWidgets('user detail narrow light', (tester) async {
    final controller = await _signedIn(FakeAdminApi());
    await _pump(
      tester,
      home: UserDetailScreen(controller: controller, userId: 'u1'),
    );
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(_golden('user_detail_narrow_light')),
    );
    await _end(tester, controller);
  }, tags: ['golden']);

  testWidgets('monitor narrow light', (tester) async {
    final controller = await _signedIn(FakeAdminApi());
    await _pump(
      tester,
      home: Scaffold(
        body: MonitorScreen(controller: controller, clock: _fixedClock),
      ),
    );
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(_golden('monitor_narrow_light')),
    );
    await _end(tester, controller);
  }, tags: ['golden']);

  testWidgets('audit narrow dark', (tester) async {
    final controller = await _signedIn(_AuditFake());
    await _pump(
      tester,
      brightness: Brightness.dark,
      home: Scaffold(body: AuditScreen(controller: controller)),
    );
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(_golden('audit_narrow_dark')),
    );
    await _end(tester, controller);
  }, tags: ['golden']);

  testWidgets('action dialog light', (tester) async {
    final controller = await _signedIn(FakeAdminApi());
    await _pump(
      tester,
      home: Builder(
        builder: (context) => Center(
          child: FilledButton(
            onPressed: () => showAdminActionDialog(
              context,
              title: 'Suspend user',
              confirmLabel: 'Suspend',
              description: 'Ada will lose access immediately.',
              destructive: true,
            ),
            child: const Text('Open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await settle(tester);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(_golden('action_dialog_light')),
    );
    await _end(tester, controller);
  }, tags: ['golden']);
}
