import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';
import 'package:karmi_app/features/admin/admin_support.dart';
import 'package:karmi_app/features/admin/admin_shell.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

import '../../support/fake_admin_api.dart';

/// Fake whose audit log and user detail are configurable per test.
class _AuditFake extends FakeAdminApi {
  _AuditFake({required this.pages});

  final Map<String?, AuditPage> pages;

  @override
  Future<AuditPage> audit(String token, {int limit = 50, String? cursor}) async {
    calls.add('audit:${cursor ?? ''}');
    return pages[cursor] ?? const AuditPage(items: []);
  }
}

class _NullUsageFake extends FakeAdminApi {
  @override
  Future<AdminUserDetail> getUser(String token, String id) async {
    final detail = await super.getUser(token, id);
    return AdminUserDetail(user: detail.user, usage: const AdminUsage());
  }
}

final List<AdminController> _live = [];

/// Runs [body], then unmounts the tree and disposes controllers so no expiry
/// timer is left pending when the framework checks invariants.

void adminTest(
  String description,
  Future<void> Function(WidgetTester tester) body,
) {
  testWidgets(description, (tester) async {
    _live.clear();
    await body(tester);
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

Future<void> pumpAdmin(
  WidgetTester tester,
  AdminController controller, {
  Size size = const Size(412, 915),
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
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: TextScaler.linear(textScale),
        ),
        child: child!,
      ),
      home: AdminShell(controller: controller),
    ),
  );
  await tester.pump();
}

Future<void> tapNav(WidgetTester tester, String label) async {
  final rail = find.byType(NavigationRail);
  final bar = find.byType(NavigationBar);
  final scope = rail.evaluate().isNotEmpty ? rail : bar;
  await tester.tap(find.descendant(of: scope, matching: find.text(label)));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

Future<void> openUser(WidgetTester tester, String name) async {
  await tester.tap(find.text(name));
  await tester.pumpAndSettle();
}

void main() {
  adminTest('users list renders fake users with status words', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();

    expect(find.text('Ada'), findsOneWidget);
    expect(find.text('Bob'), findsOneWidget);
    expect(find.text('Suspended'), findsOneWidget);
    expect(find.text('Admin console'), findsOneWidget);
    expect(find.text('Log out of admin'), findsOneWidget);
  });

  adminTest('search is debounced to 400ms and sends the query', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    api.calls.clear();

    await tester.enterText(find.widgetWithText(TextField, 'Search users'), 'bob');
    await tester.pump(const Duration(milliseconds: 300));
    expect(api.calls.where((c) => c.startsWith('list:')), isEmpty);

    await tester.pump(const Duration(milliseconds: 150));
    await tester.pump();
    expect(api.calls, contains('list:bob:::'));
    expect(find.text('Bob'), findsOneWidget);
    expect(find.text('Ada'), findsNothing);
  });

  adminTest('Load more appends the next page', (tester) async {
    final api = FakeAdminApi()..pageSize = 1;
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();

    expect(find.text('Ada'), findsOneWidget);
    expect(find.text('Bob'), findsNothing);

    await tester.tap(find.text('Load more users'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Ada'), findsOneWidget);
    expect(find.text('Bob'), findsOneWidget);
    expect(find.text('Load more users'), findsNothing);
  });

  adminTest('user detail shows usage and Unavailable for nulls', (tester) async {
    final api = _NullUsageFake();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    await openUser(tester, 'Ada');

    expect(find.text(kAdminUnavailable), findsNWidgets(4));
    expect(find.text('Requests today'), findsOneWidget);
  });

  adminTest('user detail shows usage values when present', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    await openUser(tester, 'Ada');

    expect(find.text('7'), findsOneWidget);
    expect(find.text(r'$1.50'), findsOneWidget);
    expect(find.text(r'$10.00'), findsOneWidget);
    expect(find.text(kAdminUnavailable), findsNothing);
  });

  adminTest('suspend needs a reason before confirm is enabled', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    await openUser(tester, 'Ada');

    await tester.tap(find.widgetWithText(OutlinedButton, 'Suspend'));
    await tester.pumpAndSettle();

    final confirm = find.widgetWithText(FilledButton, 'Suspend');
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(find.byType(TextField).last, '  ab  ');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(find.byType(TextField).last, 'abuse report');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);

    await tester.tap(confirm);
    await tester.pumpAndSettle();

    expect(api.calls, contains('suspend:u1:abuse report'));
    expect(find.text('User suspended.'), findsWidgets);
    expect(find.widgetWithText(OutlinedButton, 'Unsuspend'), findsOneWidget);
  });

  adminTest('export asks for a reason and sends it', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    await openUser(tester, 'Ada');

    await tester.tap(find.widgetWithText(OutlinedButton, 'Export'));
    await tester.pumpAndSettle();
    final confirm = find.widgetWithText(FilledButton, 'Export');
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(find.byType(TextField).last, 'support ticket 9');
    await tester.pump();
    await tester.tap(confirm);
    await tester.pumpAndSettle();

    expect(api.calls, contains('export:u1:support ticket 9'));
    expect(find.text('Copy'), findsOneWidget);
  });

  adminTest('delete requires typing DELETE', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    await openUser(tester, 'Bob');

    await tester.tap(find.widgetWithText(OutlinedButton, 'Delete user'));
    await tester.pumpAndSettle();
    final confirm = find.widgetWithText(FilledButton, 'Delete');
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'cleanup');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(fields.at(1), 'delete');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(fields.at(1), 'DELETE');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);

    await tester.tap(confirm);
    await tester.pumpAndSettle();

    expect(api.calls, contains('delete:u2:cleanup'));
    expect(find.text('Bob'), findsNothing);
  });

  adminTest('monitor refreshes every 5s and pauses when not resumed', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tapNav(tester, 'Monitor');

    expect(find.text('2.00%'), findsOneWidget);
    expect(find.text('Degraded'), findsOneWidget);
    expect(find.text('OK'), findsOneWidget);
    expect(api.calls.where((c) => c == 'monitor').length, 1);

    await tester.pump(const Duration(seconds: 5));
    await tester.pump();
    expect(api.calls.where((c) => c == 'monitor').length, 2);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 10));
    expect(api.calls.where((c) => c == 'monitor').length, 2);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump();
    expect(api.calls.where((c) => c == 'monitor').length, 3);
  });

  adminTest('monitor keeps last data behind a banner when refresh fails', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tapNav(tester, 'Monitor');
    expect(find.text('2.00%'), findsOneWidget);

    api.failNext = const AdminFailure(500);
    await tester.pump(const Duration(seconds: 5));
    await tester.pump();

    expect(find.text('Showing last known data'), findsOneWidget);
    expect(find.text('2.00%'), findsOneWidget);
  });

  adminTest('audit lists newest first and paginates', (tester) async {
    final api = _AuditFake(
      pages: {
        null: AuditPage(
          items: [
            AuditEntry(
              id: 'old',
              action: 'old-action',
              at: DateTime.utc(2026, 1, 1),
              reason: 'older reason',
            ),
            AuditEntry(
              id: 'new',
              action: 'new-action',
              at: DateTime.utc(2026, 2, 1),
              reason: 'newer reason',
            ),
          ],
          nextCursor: 'c2',
        ),
        'c2': const AuditPage(
          items: [AuditEntry(id: 'undated', action: 'undated-action')],
        ),
      },
    );
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tapNav(tester, 'Audit');

    final newTop = tester.getTopLeft(find.text('new-action')).dy;
    final oldTop = tester.getTopLeft(find.text('old-action')).dy;
    expect(newTop, lessThan(oldTop));
    expect(find.text('Reason: newer reason'), findsOneWidget);

    await tester.tap(find.text('Load more entries'));
    await tester.pump();
    await tester.pump();
    expect(find.text('undated-action'), findsOneWidget);
    expect(find.text('Load more entries'), findsNothing);
  });

  adminTest('unauthorized from a call ends the admin session', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tapNav(tester, 'Monitor');

    api.failNext = const AdminUnauthorized();
    await tester.pump(const Duration(seconds: 5));
    await tester.pump();

    expect(controller.token, isNull);
    expect(find.text('Admin console'), findsNothing);
  });

  adminTest('log out of admin calls logout and clears the token', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();

    await tester.tap(find.text('Log out of admin'));
    await tester.pump();
    expect(controller.token, isNull);
    expect(api.calls, contains(startsWith('close:')));
  });

  adminTest('no overflow at 200% text on phone and desktop sizes', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    for (final size in const [Size(360, 740), Size(1280, 800)]) {
      await pumpAdmin(tester, controller, size: size, textScale: 2.0);
      await tester.pump();
      expectNoOverflow(tester);

      await tapNav(tester, 'Monitor');
      expectNoOverflow(tester);

      await tapNav(tester, 'Audit');
      expectNoOverflow(tester);

      await tapNav(tester, 'Users');
      expectNoOverflow(tester);
    }
  });

  adminTest('wide layout uses a NavigationRail, narrow uses NavigationBar', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller, size: const Size(1280, 800));
    await tester.pump();
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);

    await pumpAdmin(tester, controller, size: const Size(412, 915));
    await tester.pump();
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
  });
  adminTest('tier filter dropdown sends the plan id', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    api.calls.clear();

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Yanta').last);
    await tester.pumpAndSettle();

    expect(api.calls, contains('list::yanta::'));
  });

  adminTest('change tier dialog offers plan ids and sends the choice', (tester) async {
    final api = FakeAdminApi();
    final controller = await signedIn(api);
    await pumpAdmin(tester, controller);
    await tester.pump();
    await openUser(tester, 'Ada');

    final changeTier = find.widgetWithText(OutlinedButton, 'Change tier');
    await tester.ensureVisible(changeTier);
    await tester.pump();
    await tester.tap(changeTier);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Trika').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'upgrade');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Change tier'));
    await tester.pumpAndSettle();

    expect(api.calls, contains('tier:u1:trika:upgrade'));
  });
}

void expectNoOverflow(WidgetTester tester) {
  final error = tester.takeException();
  expect(error, isNull, reason: 'layout exception: $error');
}
