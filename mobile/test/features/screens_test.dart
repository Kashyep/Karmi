import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/features/plans/plan_catalog.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/features/usage/usage_screen.dart';
import 'package:karmi_app/features/welcome/welcome_screen.dart';
import 'package:karmi_app/widgets/feedback.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

void main() {
  group('T4.1 Usage', () {
    testWidgets('loaded: plan, meter, reset and four read-only plans', (
      tester,
    ) async {
      await pumpApp(tester);
      await openTab(tester, 'Usage');
      expect(find.text('Ananta'), findsWidgets);
      expect(find.text('3 of 20 used · 17 left'), findsOneWidget);
      expect(find.byType(UsageMeter), findsOneWidget);
      expect(find.text('Available'), findsOneWidget);
      for (final plan in kPlans) {
        await tester.scrollUntilVisible(
          find.text('${plan.everydayLimit} everyday messages per day'),
          200,
          scrollable: find
              .descendant(
                of: find.byType(UsageScreen),
                matching: find.byType(Scrollable),
              )
              .first,
        );
      }
      expect(find.byType(PlanCard), findsWidgets);
      expect(find.text('Purchases unavailable'), findsWidgets);
      await expectA11yGuidelines(tester);
    });

    testWidgets('near limit and exhausted are words, not just colour', (
      tester,
    ) async {
      await pumpHost(tester, const UsageMeter(used: 17, limit: 20));
      expect(find.text('Near limit'), findsOneWidget);
      await pumpHost(tester, const UsageMeter(used: 20, limit: 20));
      expect(find.text('Allowance reached'), findsOneWidget);
    });

    testWidgets('error: "unavailable", no raw error, retry recovers', (
      tester,
    ) async {
      var calls = 0;
      final backend = FakeBackend.healthy()
        ..on('GET', '/v1/usage', (_) {
          calls++;
          return calls == 1
              ? http.Response('Internal Server Error: stack', 500)
              : jsonResponse(usageJson());
        });
      await pumpApp(tester, backend: backend);
      await openTab(tester, 'Usage');
      expect(find.text('Usage unavailable'), findsOneWidget);
      expect(find.text('Unavailable'), findsNWidgets(3));
      expect(find.textContaining('stack'), findsNothing);
      expect(find.textContaining('500'), findsNothing);
      await expectA11yGuidelines(tester);
      await tester.tap(find.text('Retry'));
      await settle(tester);
      expect(find.text('Usage unavailable'), findsNothing);
      expect(find.text('3 of 20 used · 17 left'), findsOneWidget);
    });

    testWidgets('loading shows the loader', (tester) async {
      final usage = Completer<http.Response>();
      final backend = FakeBackend.healthy()
        ..on('GET', '/v1/usage', (_) => usage.future);
      await pumpApp(tester, backend: backend);
      await openTab(tester, 'Usage');
      expect(find.text('Loading usage'), findsOneWidget);
      usage.complete(jsonResponse(usageJson()));
      await settle(tester);
      expect(find.text('Loading usage'), findsNothing);
    });
  });

  group('T4.3 Settings', () {
    testWidgets('theme segments are labelled and persist', (tester) async {
      await pumpApp(tester);
      await openTab(tester, 'Settings');
      for (final label in ['System', 'Light', 'Dark']) {
        expect(find.text(label), findsOneWidget);
      }
      await expectA11yGuidelines(tester);
      await tester.tap(find.text('Dark'));
      await settle(tester);
      expect(
        Theme.of(tester.element(find.text('Dark'))).brightness,
        Brightness.dark,
      );
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('theme_mode'), 'dark');
    });

    testWidgets('licences entry opens the licence page', (tester) async {
      await pumpApp(tester);
      await openTab(tester, 'Settings');
      await tester.tap(find.text('Licences'));
      await settle(tester);
      expect(find.byType(LicensePage), findsOneWidget);
    });

    testWidgets('sign out clears the token and returns to Welcome', (
      tester,
    ) async {
      final app = await pumpApp(tester);
      await openTab(tester, 'Settings');
      await tester.scrollUntilVisible(
        find.text('Sign out'),
        200,
        scrollable: find.byType(Scrollable).last,
      );
      await tester.tap(find.text('Sign out'));
      await settle(tester);
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(app.session.isSignedIn, isFalse);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('dev_session_token'), isNull);
      expect(find.text('Session ended'), findsNothing);
    });

    testWidgets('only the settings header is glass', (tester) async {
      await pumpApp(tester);
      await openTab(tester, 'Settings');
      expect(find.byKey(const ValueKey('settings-header')), findsOneWidget);
      expect(find.byKey(const ValueKey('karmi-glass')), findsOneWidget);
      expect(find.byType(Card), findsNWidgets(2));
    });
  });

  group('T4.4 Welcome', () {
    testWidgets('dev sign-in via POST /dev/token opens the shell', (
      tester,
    ) async {
      final app = await pumpApp(tester, signedIn: false);
      expect(find.byType(WelcomeScreen), findsOneWidget);
      await expectA11yGuidelines(tester);
      await tester.tap(find.text('Continue (development sign-in)'));
      await settle(tester);
      expect(app.session.isSignedIn, isTrue);
      expect(find.byType(WelcomeScreen), findsNothing);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('dev_session_token'), 't');
      final tokenRequest = app.backend.requests.first;
      expect(tokenRequest.url.path, '/dev/token');
    });

    testWidgets('network failure shows retry, no raw error', (tester) async {
      final backend = FakeBackend.healthy()
        ..on('POST', '/dev/token', FakeBackend.network());
      await pumpApp(tester, signedIn: false, backend: backend);
      await tester.tap(find.text('Continue (development sign-in)'));
      await settle(tester);
      expect(find.text("Can't reach Karmi"), findsOneWidget);
      expect(find.textContaining('SocketException'), findsNothing);
      expect(find.text('Retry'), findsOneWidget);
    });

    testWidgets('dev auth disabled: no sign-in button', (tester) async {
      final app = await pumpApp(tester, signedIn: false);
      await pumpHost(
        tester,
        WelcomeScreen(session: app.session, devAuthEnabled: false),
      );
      expect(find.text('Sign-in not available yet'), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
    });
  });

  group('T4.5 Tasks', () {
    testWidgets('lists tasks with state words and completes one', (
      tester,
    ) async {
      final backend = FakeBackend.healthy()
        ..on(
          'PATCH',
          '/v1/tasks/t1/complete',
          (_) => jsonResponse({
            'id': 't1',
            'title': 'Call the bank',
            'completed': true,
          }),
        );
      await pumpApp(tester, backend: backend);
      await openTab(tester, 'Tasks');
      expect(find.text('Call the bank'), findsOneWidget);
      expect(find.text('Open'), findsOneWidget);
      expect(find.text('Completed'), findsOneWidget);
      await expectA11yGuidelines(tester);
      await tester.tap(find.text('Mark complete'));
      await settle(tester);
      expect(find.text('Open'), findsNothing);
      expect(find.text('Completed'), findsNWidgets(2));
      expect(find.text('Mark complete'), findsNothing);
    });

    testWidgets('empty and error states', (tester) async {
      final backend = FakeBackend.healthy()
        ..on('GET', '/v1/tasks', (_) => jsonResponse([]));
      await pumpApp(tester, backend: backend);
      await openTab(tester, 'Tasks');
      expect(find.text('Nothing on your list yet.'), findsOneWidget);
    });

    testWidgets('load error offers retry', (tester) async {
      final backend = FakeBackend.healthy()
        ..on('GET', '/v1/tasks', (_) => jsonResponse({}, 503));
      await pumpApp(tester, backend: backend);
      await openTab(tester, 'Tasks');
      expect(find.text('Tasks unavailable'), findsOneWidget);
      expect(find.byType(ErrorBanner), findsOneWidget);
    });

    testWidgets('failed completion keeps the task open', (tester) async {
      final backend = FakeBackend.healthy()
        ..on('PATCH', '/v1/tasks/t1/complete', FakeBackend.network());
      await pumpApp(tester, backend: backend);
      await openTab(tester, 'Tasks');
      await tester.tap(find.text('Mark complete'));
      await settle(tester);
      expect(find.text('Could not complete task'), findsOneWidget);
      expect(find.text('Open'), findsOneWidget);
    });
  });

  group('T4.6 Plan selection', () {
    testWidgets('four read-only plans from plans.py, purchases unavailable', (
      tester,
    ) async {
      await pumpHost(tester, const PlanSelectionScreen(currentPlanId: 'yanta'));
      expect(kPlans.map((p) => p.label), ['Ananta', 'Yanta', 'Trika', 'Parth']);
      expect(kPlans.map((p) => p.everydayLimit), [20, 100, 250, 500]);
      expect(find.text('Current plan'), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
      await expectA11yGuidelines(tester);
    });

    testWidgets('opens from Settings', (tester) async {
      await pumpApp(tester, env: const Env(reduceTransparency: true));
      await openTab(tester, 'Settings');
      await tester.tap(find.text('Plans and access code'));
      await settle(tester);
      expect(find.byType(PlanSelectionScreen), findsOneWidget);
    });
  });

  group('text scale 2.0 has no overflow', () {
    for (final tab in ['Tasks', 'Usage', 'Settings']) {
      testWidgets(tab, (tester) async {
        await pumpApp(tester, env: const Env(textScale: 2.0));
        await openTab(tester, tab);
        expectNoOverflow(tester);
        await expectA11yGuidelines(tester);
      });
    }

    testWidgets('Welcome', (tester) async {
      await pumpApp(tester, signedIn: false, env: const Env(textScale: 2.0));
      expectNoOverflow(tester);
    });

    testWidgets('Plans', (tester) async {
      await pumpHost(
        tester,
        const PlanSelectionScreen(),
        env: const Env(textScale: 2.0),
      );
      expectNoOverflow(tester);
    });
  });
}
