import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_code_screen.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';

import '../../support/fake_admin_api.dart';
import '../../support/harness.dart';

void main() {
  testWidgets('wrong code shows the generic message and stays on screen', (
    tester,
  ) async {
    final controller = AdminController(api: FakeAdminApi());
    addTearDown(controller.dispose);
    await pumpHost(tester, AdminCodeScreen(controller: controller));

    final field = find.byKey(const ValueKey('admin_code_field'));
    final editable = tester.widget<TextField>(field);
    expect(editable.obscureText, isTrue);

    await tester.enterText(field, '000000');
    await tester.tap(find.text('Continue'));
    await settle(tester);

    expect(
      find.text('Code not accepted. Check the code and try again.'),
      findsOneWidget,
    );
    expect(find.byType(AdminCodeScreen), findsOneWidget);
    expect(controller.isActive, isFalse);
  });

  testWidgets('lockout shows the wait in minutes', (tester) async {
    final api = FakeAdminApi()..lockedOut = const Duration(minutes: 3);
    final controller = AdminController(api: api);
    addTearDown(controller.dispose);
    await pumpHost(tester, AdminCodeScreen(controller: controller));

    await tester.enterText(
      find.byKey(const ValueKey('admin_code_field')),
      '123456',
    );
    await tester.tap(find.text('Continue'));
    await settle(tester);

    expect(
      find.text('Too many attempts. Try again in 3 minutes.'),
      findsOneWidget,
    );
    expect(controller.isActive, isFalse);
  });

  testWidgets('correct code activates the session', (tester) async {
    final controller = AdminController(api: FakeAdminApi());
    addTearDown(controller.dispose);
    await pumpHost(tester, AdminCodeScreen(controller: controller));

    await tester.enterText(
      find.byKey(const ValueKey('admin_code_field')),
      '123456',
    );
    await tester.tap(find.text('Continue'));
    await settle(tester);

    expect(controller.isActive, isTrue);
    controller.reset();
  });
}
