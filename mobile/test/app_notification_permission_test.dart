import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/harness.dart';

void main() {
  group('Notification permission prompt on KarmiApp', () {
    testWidgets(
      '(a) signed-in + onboarded + flag false -> the request is called once and the flag is persisted true',
      (tester) async {
        var requestCount = 0;
        Future<bool> fakeRequest() async {
          requestCount++;
          return true;
        }

        final app = await pumpApp(
          tester,
          signedIn: true,
          notificationPermissionRequested: false,
          requestNotificationPermission: fakeRequest,
        );

        expect(find.byType(KarmiShell), findsOneWidget);
        expect(requestCount, equals(1));
        expect(app.settings.notificationPermissionRequested, isTrue);
        final prefs = await SharedPreferences.getInstance();
        expect(prefs.getBool('notification_permission_requested'), isTrue);
      },
    );

    testWidgets(
      '(b) signed-in + onboarded + flag true -> the request is never called',
      (tester) async {
        var requestCount = 0;
        Future<bool> fakeRequest() async {
          requestCount++;
          return true;
        }

        final app = await pumpApp(
          tester,
          signedIn: true,
          notificationPermissionRequested: true,
          requestNotificationPermission: fakeRequest,
        );

        expect(find.byType(KarmiShell), findsOneWidget);
        expect(requestCount, equals(0));
        expect(app.settings.notificationPermissionRequested, isTrue);
      },
    );

    testWidgets(
      '(c) the onboarding notifications step sets the flag, then completes into the shell -> the request is called exactly once in total',
      (tester) async {
        var requestCount = 0;
        Future<bool> fakeRequest() async {
          requestCount++;
          return true;
        }

        final app = await pumpApp(
          tester,
          signedIn: false,
          requestNotificationPermission: fakeRequest,
        );

        expect(find.text('Meet Karmi'), findsOneWidget);
        await tester.tap(find.text('Get Started'));
        await settle(tester);

        expect(find.text('Create your account'), findsOneWidget);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);

        expect(find.text('Know when Karmi replies'), findsOneWidget);
        expect(requestCount, equals(0));
        expect(app.settings.notificationPermissionRequested, isFalse);

        await tester.tap(
          find.byKey(const ValueKey('onboarding_allow_notifications')),
        );
        await settle(tester);

        expect(find.byType(KarmiShell), findsOneWidget);
        expect(requestCount, equals(1));
        expect(app.settings.notificationPermissionRequested, isTrue);
        final prefs = await SharedPreferences.getInstance();
        expect(prefs.getBool('notification_permission_requested'), isTrue);
      },
    );

    testWidgets(
      '(d) onboarding Maybe Later sets the flag without requesting and mounts the shell',
      (tester) async {
        var requestCount = 0;
        Future<bool> fakeRequest() async {
          requestCount++;
          return true;
        }

        final app = await pumpApp(
          tester,
          signedIn: false,
          requestNotificationPermission: fakeRequest,
        );

        expect(find.text('Meet Karmi'), findsOneWidget);
        await tester.tap(find.text('Get Started'));
        await settle(tester);

        expect(find.text('Create your account'), findsOneWidget);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);

        expect(find.text('Know when Karmi replies'), findsOneWidget);
        expect(requestCount, equals(0));
        expect(app.settings.notificationPermissionRequested, isFalse);

        expect(find.text('Maybe Later'), findsOneWidget);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_skip_notifications')),
        );
        await settle(tester);

        expect(find.byType(KarmiShell), findsOneWidget);
        expect(requestCount, equals(0));
        expect(app.settings.notificationPermissionRequested, isTrue);
        final prefs = await SharedPreferences.getInstance();
        expect(prefs.getBool('notification_permission_requested'), isTrue);
      },
    );
  });
}
