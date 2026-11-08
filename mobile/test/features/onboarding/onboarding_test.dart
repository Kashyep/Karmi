import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/auth/clerk_email_code_actions.dart';
import 'package:karmi_app/features/onboarding/onboarding.dart';
import 'package:karmi_app/features/onboarding/widgets/account_auth_step.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fake_backend.dart';
import '../../support/fake_clerk_actions.dart';
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
            totalSteps: 4,
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

  group('OnboardingFlow Integration — 4-step flow', () {
    testWidgets(
      'full flow: welcome -> auth (dev sign-in) -> plan chooser -> notifications -> complete',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        bool completed = false;
        String? completedPlan;
        int permissionCalls = 0;

        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: true,
            requestNotificationPermission: () async {
              permissionCalls++;
              return true;
            },
            onComplete: (plan) {
              completed = true;
              completedPlan = plan;
            },
          ),
        );

        // Step 0: Welcome
        expect(find.text('Meet Karmi'), findsOneWidget);
        await tester.tap(find.text('Get Started'));
        await settle(tester);

        // Step 1: Auth (dev sign in)
        expect(find.text('Create your account'), findsOneWidget);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);

        // Step 2: Plan Chooser (defaults to Ananta)
        expect(find.text('Choose your plan'), findsOneWidget);
        expect(find.text('Ananta (Free)'), findsOneWidget);
        expect(find.text('Yanta'), findsOneWidget);
        expect(find.text('Trika'), findsOneWidget);
        expect(find.text('Parth'), findsOneWidget);
        // Plan chooser has no back button: signed-in users cannot step back to auth
        expect(find.byIcon(Icons.arrow_back), findsNothing);
        // Continue with default Ananta plan
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);

        // Step 3: Notifications
        expect(find.text('Know when Karmi replies'), findsOneWidget);

        // In-app back returns to plan chooser
        await tester.tap(find.byIcon(Icons.arrow_back));
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);

        // Advance back to notifications
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);

        // Tap Allow Notifications: calls permission callback once, finishes
        await tester.tap(
          find.byKey(const ValueKey('onboarding_allow_notifications')),
        );
        await settle(tester);

        expect(permissionCalls, 1);
        expect(completed, isTrue);
        expect(completedPlan, isNull);
        expect(settings.hasCompletedOnboarding, isTrue);
        expect(settings.onboardingStep, 0);
      },
    );

    testWidgets('sign-in (details == null) lands on plan chooser', (
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

      final flowKey = GlobalKey();
      await pumpHost(
        tester,
        OnboardingFlow(
          key: flowKey,
          session: session,
          settings: settings,
          devAuthEnabled: true,
        ),
      );

      // Navigate to Auth step
      await tester.tap(find.text('Get Started'));
      await settle(tester);
      expect(find.text('Create your account'), findsOneWidget);

      final authStep = tester.widget<AccountAuthStep>(
        find.byType(AccountAuthStep),
      );
      authStep.onSignedIn(null);
      await settle(tester);
      // Must land directly on plan chooser
      expect(find.text('Choose your plan'), findsOneWidget);
    });

    testWidgets('sign-up lands on plan chooser and updates profile', (
      tester,
    ) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = KarmiSettings(prefs);
      String? savedDisplayName;
      final backend = FakeBackend.healthy()
        ..on('PATCH', '/v1/user/profile', (req) {
          final data = jsonDecode(req.body) as Map<String, dynamic>;
          savedDisplayName = data['display_name'] as String?;
          return jsonResponse({'status': 'ok'});
        });
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
      final authStep = tester.widget<AccountAuthStep>(
        find.byType(AccountAuthStep),
      );
      authStep.onSignedIn(
        const AccountDetails(firstName: 'Jane', lastName: 'Doe'),
      );
      await settle(tester);
      expect(savedDisplayName, 'Jane Doe');
      expect(find.text('Choose your plan'), findsOneWidget);
    });

    testWidgets(
      'choosing Ananta -> notifications -> onComplete called with no upgrade',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        String? completedPlan = 'sentinel';
        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: true,
            onComplete: (plan) => completedPlan = plan,
          ),
        );

        // Go to auth -> plan chooser
        await tester.tap(find.text('Get Started'));
        await settle(tester);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);

        // Ananta is preselected, continue
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);

        // Maybe Later
        await tester.tap(
          find.byKey(const ValueKey('onboarding_skip_notifications')),
        );
        await settle(tester);

        expect(completedPlan, isNull);
      },
    );

    testWidgets(
      'choosing a paid plan -> notifications -> onComplete called with that plan',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        String? completedPlan;
        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: true,
            onComplete: (plan) => completedPlan = plan,
          ),
        );

        await tester.tap(find.text('Get Started'));
        await settle(tester);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);

        // Select Trika
        await tester.tap(find.byKey(const ValueKey('plan_choice_trika')));
        await settle(tester);

        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);

        // Allow notifications
        await tester.tap(
          find.byKey(const ValueKey('onboarding_allow_notifications')),
        );
        await settle(tester);

        expect(completedPlan, 'trika');
      },
    );

    testWidgets(
      'Allow calls the injected permission callback once then completes',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        int permissionCalls = 0;
        bool completed = false;

        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: true,
            requestNotificationPermission: () async {
              permissionCalls++;
              return false; // even if user denies, onboarding completes
            },
            onComplete: (_) => completed = true,
          ),
        );

        await tester.tap(find.text('Get Started'));
        await settle(tester);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_allow_notifications')),
        );
        await settle(tester);

        expect(permissionCalls, 1);
        expect(completed, isTrue);
      },
    );

    testWidgets(
      'back navigation: auth steps back to welcome, plan chooser has no back button and system back exits, notifications steps back to plan',
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

        // Step 0: Welcome
        expect(find.text('Meet Karmi'), findsOneWidget);

        // System back at Step 0: canPop is true (exits app)
        final didHandleAtZero = await WidgetsBinding.instance.handlePopRoute();
        expect(didHandleAtZero, isFalse);

        // Move to Step 1: Auth
        await tester.tap(find.text('Get Started'));
        await settle(tester);
        expect(find.text('Create your account'), findsOneWidget);

        // System back at Step 1: steps back to Welcome
        final didHandleAtOne = await WidgetsBinding.instance.handlePopRoute();
        expect(didHandleAtOne, isTrue);
        await settle(tester);
        expect(find.text('Meet Karmi'), findsOneWidget);

        // In-app back arrow at Step 1: also steps back to Welcome
        await tester.tap(find.text('Get Started'));
        await settle(tester);
        expect(find.text('Create your account'), findsOneWidget);
        await tester.tap(find.byIcon(Icons.arrow_back));
        await settle(tester);
        expect(find.text('Meet Karmi'), findsOneWidget);

        // Advance to Step 2: Plan chooser via dev sign-in
        await tester.tap(find.text('Get Started'));
        await settle(tester);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);

        // Step 2: No in-app back arrow, cannot go back to auth step
        expect(find.byIcon(Icons.arrow_back), findsNothing);

        // Step 2: System back is not intercepted (canPop: true, exits app)
        final didHandleAtTwo = await WidgetsBinding.instance.handlePopRoute();
        expect(didHandleAtTwo, isFalse);
        expect(find.text('Choose your plan'), findsOneWidget);

        // Advance to Step 3: Notifications
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);

        // System back at Step 3: steps back to Plan chooser
        final didHandleAtThree = await WidgetsBinding.instance.handlePopRoute();
        expect(didHandleAtThree, isTrue);
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);

        // Advance to Step 3 again and test in-app arrow: steps back to Plan chooser
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);
        await tester.tap(find.byIcon(Icons.arrow_back));
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);
      },
    );

    testWidgets(
      'signed-out session + saved step 3 shows auth or welcome, not Stay updated',
      (tester) async {
        for (final savedStep in [2, 3, 5, 6]) {
          SharedPreferences.setMockInitialValues({
            'onboarding_active_step': savedStep,
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
            OnboardingFlow(session: session, settings: settings),
          );
          await settle(tester);
          expect(find.text('Know when Karmi replies'), findsNothing);
          expect(find.text('Choose your plan'), findsNothing);
          expect(find.text('Create your account'), findsOneWidget);
        }
      },
    );

    testWidgets(
      'legacy saved step 5/6 for signed-in user resumes at plan chooser, never out of range',
      (tester) async {
        for (final staleStep in [2, 4, 5, 6, 99]) {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setInt('onboarding_active_step', staleStep);
          await prefs.setString(
            'dev_session_token',
            'dev_user|role|9999999999|1|sig',
          );
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
          await settle(tester);

          expect(find.text('Choose your plan'), findsOneWidget);
        }
      },
    );

    testWidgets(
      'saved step 3 for signed-in user resumes at notifications step',
      (tester) async {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setInt('onboarding_active_step', 3);
        await prefs.setString(
          'dev_session_token',
          'dev_user|role|9999999999|1|sig',
        );
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
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);
      },
    );

    testWidgets(
      'signed-in users resuming onboarding must never see Welcome or Auth',
      (tester) async {
        for (final step in [0, 1]) {
          SharedPreferences.setMockInitialValues({
            'onboarding_active_step': step,
            'dev_session_token': 'active-token',
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
            OnboardingFlow(session: session, settings: settings),
          );
          await settle(tester);

          expect(find.text('Meet Karmi'), findsNothing);
          expect(find.text('Create your account'), findsNothing);
          expect(find.text('Choose your plan'), findsOneWidget);
        }
      },
    );
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
            devAuthEnabled: false,
          ),
        );

        expect(find.text('Meet Karmi'), findsOneWidget);
        await tester.tap(find.text('Get Started'));
        await settle(tester);

        expect(find.text('Create your account'), findsOneWidget);
        expect(find.text('Continue (development sign-in)'), findsNothing);
        expect(
          find.byKey(const ValueKey('onboarding_dev_signin')),
          findsNothing,
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

  group('OnboardingFlow Plan Chooser Pricing', () {
    testWidgets('renders server price ₹70 / month and no \$', (tester) async {
      SharedPreferences.setMockInitialValues({
        'onboarding_active_step': 2,
        'dev_session_token': 'dev_user|role|9999999999|1|sig',
      });
      final prefs = await SharedPreferences.getInstance();
      final settings = KarmiSettings(prefs);
      final backend = FakeBackend.healthy();
      backend.on(
        'GET',
        '/v1/plans',
        (_) => jsonResponse([
          {
            'id': 'ananta',
            'label': 'Ananta',
            'price_inr': 0,
            'everyday_limit': 20,
          },
          {
            'id': 'yanta',
            'label': 'Yanta',
            'price_inr': 70,
            'everyday_limit': 50,
          },
        ]),
      );
      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        prefs: prefs,
      );

      await pumpHost(
        tester,
        OnboardingFlow(session: session, settings: settings),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('₹70 / month'), findsOneWidget);
      expect(find.text('Free • 20 everyday messages/day'), findsOneWidget);
      expect(find.textContaining(r'$'), findsNothing);
      expect(find.textContaining('USD'), findsNothing);
    });

    testWidgets(
      'shows Price unavailable and never a fabricated number when server fails',
      (tester) async {
        SharedPreferences.setMockInitialValues({
          'onboarding_active_step': 2,
          'dev_session_token': 'dev_user|role|9999999999|1|sig',
        });
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        backend.on(
          'GET',
          '/v1/plans',
          (_) => jsonResponse({'detail': 'server error'}, 500),
        );
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );
        await pumpHost(
          tester,
          OnboardingFlow(session: session, settings: settings),
        );
        await tester.pumpAndSettle();

        expect(find.text('Free • 20 everyday messages/day'), findsOneWidget);
        expect(find.textContaining('Price unavailable'), findsWidgets);
        expect(find.textContaining(r'$'), findsNothing);
      },
    );
  });

  group('KarmiApp End-to-End Onboarding Flow & Plan Selection Hand-off', () {
    testWidgets(
      'choosing a paid plan opens plan selection screen for it on app entry',
      (tester) async {
        await pumpApp(tester, signedIn: false);

        expect(find.text('Meet Karmi'), findsOneWidget);
        await tester.tap(find.text('Get Started'));
        await settle(tester);

        expect(find.text('Create your account'), findsOneWidget);
        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
        // Select Yanta
        await tester.tap(find.byKey(const ValueKey('plan_choice_yanta')));
        await settle(tester);

        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_skip_notifications')),
        );
        await settle(tester);

        // Now inside the app: KarmiShell was mounted, and PlanSelectionScreen was pushed on top
        expect(find.byType(PlanSelectionScreen), findsOneWidget);
        // And the preselected plan (yanta) is highlighted
        expect(
          find.byKey(const ValueKey('plan_card_yanta_highlighted')),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'choosing Ananta finishes onboarding directly into app without opening plan screen',
      (tester) async {
        await pumpApp(tester, signedIn: false);

        await tester.tap(find.text('Get Started'));
        await settle(tester);

        await tester.tap(find.text('Continue (development sign-in)'));
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
        // Ananta is default
        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_skip_notifications')),
        );
        await settle(tester);

        // Inside app, PlanSelectionScreen is NOT opened
        expect(find.byType(PlanSelectionScreen), findsNothing);
        expect(find.byType(KarmiShell), findsOneWidget);
      },
    );

    testWidgets(
      'delayed-prefs finish still delivers yanta to onComplete even when unmounted',
      (tester) async {
        String? completedPlan;
        SharedPreferences.setMockInitialValues({
          'onboarding_active_step': 2,
          'dev_session_token': 'dev_user!role!9999999999!sig',
        });
        final prefs = await SharedPreferences.getInstance();
        final settings = _DelayedSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          prefs: prefs,
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        );

        Widget host(Widget child) => MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: child,
        );

        await tester.pumpWidget(
          host(
            ListenableBuilder(
              listenable: settings,
              builder: (context, _) {
                if (settings.hasCompletedOnboarding) {
                  return const Scaffold(body: Text('App Shell'));
                }
                return OnboardingFlow(
                  session: session,
                  settings: settings,
                  onComplete: (plan) => completedPlan = plan,
                );
              },
            ),
          ),
        );
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
        // Select Yanta
        await tester.tap(find.byKey(const ValueKey('plan_choice_yanta')));
        await settle(tester);

        await tester.tap(
          find.byKey(const ValueKey('onboarding_plan_continue')),
        );
        await settle(tester);
        expect(find.text('Know when Karmi replies'), findsOneWidget);
        final completer = Completer<void>();
        settings.writeCompleter = completer;

        // Tap Maybe Later to finish onboarding
        await tester.tap(
          find.byKey(const ValueKey('onboarding_skip_notifications')),
        );
        // Pump frame while setHasCompletedOnboarding is suspended.
        // ListenableBuilder catches notifyListeners() and unmounts OnboardingFlow.
        await tester.pump();
        expect(find.text('App Shell'), findsOneWidget);

        // Complete the prefs write
        completer.complete();
        await settle(tester);

        expect(completedPlan, 'yanta');
      },
    );

    testWidgets(
      'session observer moves to step 2 when signed in externally at step < 2',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          prefs: prefs,
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        );

        Widget host(Widget child) => MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: child,
        );

        await tester.pumpWidget(
          host(OnboardingFlow(session: session, settings: settings)),
        );
        await settle(tester);
        expect(find.text('Meet Karmi'), findsOneWidget);

        await session.signInWithDevToken();
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
      },
    );

    testWidgets(
      'session observer resets to step 0 when signed out externally at step >= 2',
      (tester) async {
        SharedPreferences.setMockInitialValues({
          'onboarding_active_step': 2,
          'dev_session_token': 'dev_user!role!9999999999!sig',
        });
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          prefs: prefs,
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        );

        Widget host(Widget child) => MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: child,
        );

        await tester.pumpWidget(
          host(OnboardingFlow(session: session, settings: settings)),
        );
        await settle(tester);
        expect(find.text('Choose your plan'), findsOneWidget);

        await session.signOut();
        await settle(tester);

        expect(find.text('Meet Karmi'), findsOneWidget);
      },
    );

    testWidgets(
      'sign-up keeps display name when session flips signed-in mid-verify',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        String? savedDisplayName;
        final backend = FakeBackend.healthy();
        backend.on('PATCH', '/v1/user/profile', (request) {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          savedDisplayName = body['display_name'] as String?;
          return jsonResponse({'id': 'u', 'display_name': savedDisplayName});
        });
        final session = KarmiSession(
          prefs: prefs,
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        );
        final fake = _SessionFlippingFakeClerkActions(session: session);

        Widget host(Widget child) => MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: child,
        );

        await tester.pumpWidget(
          host(
            OnboardingFlow(
              session: session,
              settings: settings,
              clerkActions: fake,
              devAuthEnabled: false,
            ),
          ),
        );
        await settle(tester);

        await tester.tap(find.text('Get Started'));
        await settle(tester);

        await _fillCreateAccountAndCode(tester);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_auth_continue')),
        );
        // Real Clerk notifies signed-in and frames render while the verify
        // call is still in flight; only then does the call return.
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 50));
        fake.verifyGate.complete();
        await settle(tester);

        expect(savedDisplayName, 'Jane Doe');
        expect(find.text('Choose your plan'), findsOneWidget);
      },
    );

    testWidgets(
      'updateProfile never completing still advances to choose your plan on sign up',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final completer = Completer<http.Response>();
        final backend = FakeBackend.healthy();
        backend.on('PATCH', '/v1/user/profile', (_) => completer.future);
        final fake = FakeClerkEmailCodeActions();
        final session = KarmiSession(
          prefs: prefs,
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
        );

        Widget host(Widget child) => MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: child,
        );

        await tester.pumpWidget(
          host(
            OnboardingFlow(
              session: session,
              settings: settings,
              clerkActions: fake,
              devAuthEnabled: false,
            ),
          ),
        );
        await settle(tester);

        await tester.tap(find.text('Get Started'));
        await settle(tester);

        await _fillCreateAccountAndCode(tester);
        await tester.tap(
          find.byKey(const ValueKey('onboarding_auth_continue')),
        );
        await settle(tester);

        expect(find.text('Choose your plan'), findsOneWidget);
        completer.complete(
          jsonResponse({'id': 'u', 'display_name': 'Jane Doe'}),
        );
      },
    );
  });
}

class _DelayedSettings extends KarmiSettings {
  _DelayedSettings(super.prefs);
  Completer<void>? writeCompleter;
  bool _completed = false;

  @override
  bool get hasCompletedOnboarding => _completed || super.hasCompletedOnboarding;

  @override
  Future<void> setHasCompletedOnboarding(bool value) async {
    _completed = value;
    notifyListeners();
    if (writeCompleter != null) {
      await writeCompleter!.future;
    }
    await super.setHasCompletedOnboarding(value);
  }
}

/// Fills the create-account form, submits it and types the email code,
/// leaving the code submit to the caller.
Future<void> _fillCreateAccountAndCode(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_first_name_field')),
    'Jane',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_last_name_field')),
    'Doe',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_username_field')),
    'janedoe',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_email_field')),
    'jane@example.com',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_password_field')),
    'Sunrise#42',
  );
  await tester.tap(find.byKey(const ValueKey('onboarding_auth_continue')));
  await settle(tester);

  await tester.enterText(
    find.byKey(const ValueKey('onboarding_otp_field')),
    '424242',
  );
}

class _SessionFlippingFakeClerkActions extends FakeClerkEmailCodeActions {
  _SessionFlippingFakeClerkActions({required this.session});

  final KarmiSession session;
  final verifyGate = Completer<void>();

  @override
  Future<void> verifySignUpCode(
    String code,
    ClerkFlowErrorHandler onError,
  ) async {
    await session.signInWithDevToken();
    await verifyGate.future;
    return super.verifySignUpCode(code, onError);
  }
}
