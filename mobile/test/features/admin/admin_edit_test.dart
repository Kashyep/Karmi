import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';
import 'package:karmi_app/features/admin/admin_shell.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import '../../support/fake_admin_api.dart';

Future<void> pump(WidgetTester t, FakeAdminApi api, AdminController c) async {
  await c.verifyCode(api.code);
  t.view.physicalSize = const Size(412, 915);
  t.view.devicePixelRatio = 1;
  await t.pumpWidget(MaterialApp(theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light), home: AdminShell(controller: c)));
  await t.pumpAndSettle();
}

void main() {
  testWidgets('edit profile sends reason', (t) async {
    final api = FakeAdminApi(); final c = AdminController(api: api); addTearDown(c.dispose);
    await pump(t, api, c); await t.tap(find.text('Ada')); await t.pumpAndSettle();
    await t.tap(find.widgetWithText(OutlinedButton, 'Edit profile')); await t.pumpAndSettle();
    final save = find.widgetWithText(FilledButton, 'Save');
    expect(t.widget<FilledButton>(save).onPressed, isNull);
    await t.enterText(find.byType(TextField).last, 'support request'); await t.tap(save); await t.pumpAndSettle();
    expect(api.calls, contains('edit:u1:support request'));
  });

  testWidgets('promote sends tier and reason', (t) async {
    final api = FakeAdminApi(); final c = AdminController(api: api); addTearDown(c.dispose);
    await pump(t, api, c); await t.tap(find.text('Ada')); await t.pumpAndSettle();
    await t.tap(find.widgetWithText(OutlinedButton, 'Promote')); await t.pumpAndSettle();
    await t.enterText(find.byType(TextField).last, 'upgrade request');
    await t.tap(find.widgetWithText(FilledButton, 'Set plan')); await t.pumpAndSettle();
    expect(api.calls.any((x) => x.contains('tier:u1:yanta')), isTrue);
  });

  testWidgets('reason required blocks mutation', (t) async {
    final api = FakeAdminApi(); final c = AdminController(api: api); addTearDown(c.dispose);
    await pump(t, api, c); await t.tap(find.text('Ada')); await t.pumpAndSettle();
    await t.tap(find.widgetWithText(OutlinedButton, 'Promote')); await t.pumpAndSettle();
    expect(t.widget<FilledButton>(find.widgetWithText(FilledButton, 'Set plan')).onPressed, isNull);
    expect(api.calls.where((x) => x.startsWith('tier:')), isEmpty);
  });

  testWidgets('filter chips reload list', (t) async {
    final api = FakeAdminApi(); final c = AdminController(api: api); addTearDown(c.dispose);
    await pump(t, api, c);
    await t.tap(find.text('Suspended')); await t.pump();
    await t.tap(find.text('Expiring soon')); await t.pump();
    await t.tap(find.text('Tester label')); await t.pumpAndSettle();
    await t.enterText(find.byType(TextField).last, 'qa'); await t.tap(find.text('Apply')); await t.pump();
    expect(api.calls.where((x) => x.startsWith('list:')).length, greaterThan(1));
  });
}
