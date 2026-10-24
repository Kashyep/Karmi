@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';
import 'package:karmi_app/features/admin/user_detail_screen.dart';
import 'package:karmi_app/features/admin/users_screen.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

import '../../support/fake_admin_api.dart';

Future<void> pumpDetail(WidgetTester tester, Brightness brightness) async {
  final api = FakeAdminApi();
  final controller = AdminController(api: api);
  await controller.verifyCode(api.code);
  addTearDown(controller.dispose);
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, brightness),
      home: UserDetailScreen(controller: controller, userId: 'u1'),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> pumpUsers(WidgetTester tester, Brightness brightness) async {
  final api = FakeAdminApi();
  final controller = AdminController(api: api);
  await controller.verifyCode(api.code);
  addTearDown(controller.dispose);
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, brightness),
      home: Scaffold(body: UsersScreen(controller: controller)),
    ),
  );
  await tester.pumpAndSettle();
  for (final name in ['Ada', 'Bob']) {
    await tester.ensureVisible(find.text(name));
    await tester.longPress(find.text(name));
    await tester.pump();
  }
  await tester.tap(find.widgetWithText(FilledButton, 'Set plan (2)'));
  await tester.pumpAndSettle();
}

void main() {
  for (final brightness in Brightness.values) {
    final suffix = brightness == Brightness.light ? 'light' : 'dark';
    testWidgets('user detail plan card $suffix', (tester) async {
      await pumpDetail(tester, brightness);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/linux/admin_user_detail_plan_$suffix.png'),
      );
      await tester.pump(const Duration(minutes: 16));
    });

    testWidgets('bulk set-plan sheet $suffix', (tester) async {
      await pumpUsers(tester, brightness);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/linux/admin_bulk_set_plan_$suffix.png'),
      );
      await tester.pump(const Duration(minutes: 16));
    });
  }
}
