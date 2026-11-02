import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/onboarding/onboarding.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fake_backend.dart';
import '../../support/harness.dart';

void main() {
  group('Onboarding Widgets', () {
    testWidgets('PillCta states (enabled, loading, disabled)', (tester) async {
      bool tapped = false;
      await pumpHost(
        tester,
        Column(
          children: [
            PillCta(label: 'Continue', onPressed: () => tapped = true),
            const SizedBox(height: 10),
            const PillCta(label: 'Loading', onPressed: null, isLoading: true),
            const SizedBox(height: 10),
            PillCta(
              label: 'Disabled',
              onPressed: () => tapped = true,
              enabled: false,
            ),
          ],
        ),
      );

      expect(find.text('Continue'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('Disabled'), findsOneWidget);

      await tester.tap(find.text('Continue'));
      expect(tapped, isTrue);
    });

    testWidgets('ChoiceTile selection and tap', (tester) async {
      bool selected = false;
      await pumpHost(
        tester,
        ChoiceTile(
          title: 'Concise',
          description: 'Short direct answers',
          isSelected: true,
          onTap: () => selected = true,
        ),
      );

      expect(find.text('Concise'), findsOneWidget);
      expect(find.text('Short direct answers'), findsOneWidget);
      expect(find.byIcon(Icons.check), findsOneWidget);

      await tester.tap(find.text('Concise'));
      expect(selected, isTrue);
    });

    testWidgets(
      'OnboardingScaffold renders progress, back button, offline banner',
      (tester) async {
        bool backCalled = false;
        await pumpHost(
          tester,
          OnboardingScaffold(
            currentStep: 1,
            totalSteps: 5,
            isOffline: true,
            onBack: () => backCalled = true,
            body: const Text('Step body'),
          ),
        );

        expect(
          find.text('Offline. Reconnecting when internet is restored...'),
          findsOneWidget,
        );
        expect(find.text('Step body'), findsOneWidget);
        expect(find.byIcon(Icons.arrow_back), findsOneWidget);

        await tester.tap(find.byIcon(Icons.arrow_back));
        expect(backCalled, isTrue);
      },
    );
  });

  group('OnboardingFlow Integration', () {
    testWidgets('navigation, validation, back navigation, and dev sign-in', (
      tester,
    ) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = KarmiSettings(prefs);
      final backend = FakeBackend.healthy();
      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        prefs: prefs,
      );

      await pumpHost(
        tester,
        OnboardingFlow(
          session: session,
          settings: settings,
          devAuthEnabled: true,
        ),
      );

      // Step 0: Welcome
      expect(find.text('Meet Karmi'), findsOneWidget);
      await tester.tap(find.text('Get Started'));
      await settle(tester);

      // Step 1: Auth (Dev sign-in)
      expect(find.text('Create your account'), findsOneWidget);
      await tester.tap(find.text('Continue (development sign-in)'));
      await settle(tester);

      // Profile step
      expect(find.text('What should we call you?'), findsOneWidget);

      // Profile validation: empty first name
      await tester.tap(find.text('Continue'));
      await settle(tester);
      expect(
        find.text('First name must be at least 2 characters.'),
        findsOneWidget,
      );

      // Enter first name
      await tester.enterText(find.byType(TextField).first, 'Alice');
      await tester.tap(find.text('Continue'));
      await settle(tester);

      // Preferences step
      expect(find.text('Choose your model approach'), findsOneWidget);
      await tester.tap(find.text('Continue'));
      await settle(tester);

      // Plan intro step
      expect(find.text("You're starting on Ananta Free"), findsOneWidget);
      await tester.tap(find.text('Continue with Ananta Free'));
      await settle(tester);

      // Permissions step
      expect(find.text('Stay updated on background tasks'), findsOneWidget);
      await tester.tap(find.text('Allow Notifications'));
      await settle(tester);

      // Complete step
      expect(find.text("You're all set!"), findsOneWidget);
      await tester.tap(find.text('Enter Karmi'));
      await settle(tester);
      expect(settings.hasCompletedOnboarding, isTrue);
    });

    testWidgets('resume persistence from saved step', (tester) async {
      SharedPreferences.setMockInitialValues({'onboarding_active_step': 2});
      final prefs = await SharedPreferences.getInstance();
      final settings = KarmiSettings(prefs);
      final backend = FakeBackend.healthy();
      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        prefs: prefs,
      );

      await pumpHost(
        tester,
        OnboardingFlow(session: session, settings: settings),
      );

      // Should resume at step 2 (Profile step)
      expect(find.text('What should we call you?'), findsOneWidget);
    });
  });

  group('OnboardingFlow Auth Step — dev sign-in gate', () {
    testWidgets(
      'dev sign-in button is hidden when devAuthEnabled is false (release mode)',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: false, // simulates kReleaseMode / dart-define gate
          ),
        );

        // Navigate to auth step
        expect(find.text('Meet Karmi'), findsOneWidget);
        await tester.tap(find.text('Get Started'));
        await settle(tester);

        // Auth step visible but dev sign-in button must be absent
        expect(find.text('Create your account'), findsOneWidget);
        expect(find.text('Continue (development sign-in)'), findsNothing);
        expect(
          find.byKey(const ValueKey('onboarding_dev_signin')),
          findsNothing,
        );
        await tester.enterText(
          find.byKey(const ValueKey('onboarding_email_field')),
          'release@example.com',
        );
        await tester.tap(
          find.byKey(const ValueKey('onboarding_auth_continue')),
        );
        await settle(tester);
        expect(
          find.text('Clerk authentication is not configured.'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'dev sign-in button is shown when devAuthEnabled is true (debug/profile mode)',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: true,
          ),
        );

        await tester.tap(find.text('Get Started'));
        await settle(tester);

        expect(
          find.byKey(const ValueKey('onboarding_dev_signin')),
          findsOneWidget,
        );
      },
    );
  });
}
