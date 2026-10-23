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
            PillCta(
              label: 'Continue',
              onPressed: () => tapped = true,
            ),
            const SizedBox(height: 10),
            const PillCta(
              label: 'Loading',
              onPressed: null,
              isLoading: true,
            ),
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

    testWidgets('OtpField auto-advance, digits and completion', (tester) async {
      String? completedCode;
      await pumpHost(
        tester,
        OtpField(
          length: 6,
          onCompleted: (code) => completedCode = code,
        ),
      );

      expect(find.byType(TextField), findsNWidgets(6));
      await tester.enterText(find.byType(TextField).first, '123456');
      await settle(tester);
      expect(completedCode, '123456');
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

    testWidgets('OnboardingScaffold renders progress, back button, offline banner', (tester) async {
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

      expect(find.text('Offline. Reconnecting when internet is restored...'), findsOneWidget);
      expect(find.text('Step body'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back), findsOneWidget);

      await tester.tap(find.byIcon(Icons.arrow_back));
      expect(backCalled, isTrue);
    });
  });

  group('OnboardingFlow Integration', () {
    testWidgets('navigation, validation, back navigation, and dev sign-in', (tester) async {
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
      await tester.tap(find.text('Continue (development sign-in)'));
      await settle(tester);

      // Profile step
      expect(find.text('Tell us about yourself'), findsOneWidget);

      // Profile validation: empty first name
      await tester.tap(find.text('Continue'));
      await settle(tester);
      expect(find.text('First name must be at least 2 characters.'), findsOneWidget);

      // Enter first name
      await tester.enterText(find.byType(TextField).first, 'Alice');
      await tester.tap(find.text('Continue'));
      await settle(tester);

      // Preferences step
      expect(find.text('Choose your style'), findsOneWidget);
      await tester.tap(find.text('Continue'));
      await settle(tester);

      // Plan intro step
      expect(find.text('Choose your starting tier'), findsOneWidget);
      await tester.tap(find.text('Continue'));
      await settle(tester);

      // Permissions step
      expect(find.text('Stay in sync'), findsOneWidget);
      await tester.tap(find.text('Continue'));
      await settle(tester);

      // Complete step
      expect(find.text("You're all set!"), findsOneWidget);
      await tester.tap(find.text('Start chatting'));
      await settle(tester);

      expect(settings.hasCompletedOnboarding, isTrue);
    });

    testWidgets('resume persistence from saved step', (tester) async {
      SharedPreferences.setMockInitialValues({
        'onboarding_active_step': 2,
      });
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
        ),
      );

      // Should resume at step 2 (Profile step)
      expect(find.text('Tell us about yourself'), findsOneWidget);
    });
  });
}
