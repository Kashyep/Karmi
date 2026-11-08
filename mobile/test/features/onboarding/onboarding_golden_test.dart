/// Comprehensive golden tests for every onboarding screen.
///
/// Screens covered (light + dark, x1.0 glass):
///   welcome, create_account, sign_in, otp, plan_chooser, notifications
///
/// Extra cases:
///   create_account_x2.0  — create-account step at text scale 2.0 (overflow gate)
///   plan_chooser_x2.0    — plan chooser step at text scale 2.0 (overflow gate)
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/onboarding/onboarding.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fake_backend.dart';
import '../../support/fake_clerk_actions.dart';
import '../../support/harness.dart';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Builds a session+settings starting at [step] and returns the golden-ready
/// [OnboardingFlow] widget. Clerk is always the in-memory fake.
Future<(KarmiSettings, KarmiSession, OnboardingFlow)> _setup(
  int step, {
  bool devAuthEnabled = false,
}) async {
  SharedPreferences.setMockInitialValues({
    if (step > 0) 'onboarding_active_step': step,
    if (step >= 2) 'dev_session_token': 'dev_user|role|9999999999|1|sig',
  });
  final prefs = await SharedPreferences.getInstance();
  final settings = KarmiSettings(prefs);
  final backend = FakeBackend.healthy();
  final session = KarmiSession(
    api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
    prefs: prefs,
  );
  final widget = OnboardingFlow(
    session: session,
    settings: settings,
    devAuthEnabled: devAuthEnabled,
    clerkActions: FakeClerkEmailCodeActions(),
  );
  return (settings, session, widget);
}

/// Welcome → Get Started, landing on the create-account step.
Future<void> _openCreateAccount(WidgetTester tester) async {
  await tester.tap(find.text('Get Started'));
  await settle(tester);
  expect(find.text('Create your account'), findsOneWidget);
}

Future<void> _fillCreateAccount(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_first_name_field')),
    'Alice',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_username_field')),
    'alice_k',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_email_field')),
    'alice@example.com',
  );
  await tester.enterText(
    find.byKey(const ValueKey('onboarding_password_field')),
    'Sunrise#42',
  );
}

// ---------------------------------------------------------------------------
// Golden tests
// ---------------------------------------------------------------------------

void main() {
  const phoneSize = Size(390, 844);

  for (final brightness in [Brightness.light, Brightness.dark]) {
    final b = brightness.name;

    // ── Welcome (step 0) ────────────────────────────────────────────────────
    testWidgets('golden onboarding_welcome_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(0);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text('Meet Karmi'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_welcome_${b}_x1.0_glass')),
      );
    });

    // ── Create account (step 1) ─────────────────────────────────────────────
    testWidgets('golden onboarding_create_account_${b}_x1.0_glass', (
      tester,
    ) async {
      final (_, _, widget) = await _setup(0);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      await _openCreateAccount(tester);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(
          goldenPath('onboarding_create_account_${b}_x1.0_glass'),
        ),
      );
    });

    // ── Sign in (step 1, sign-in mode) ──────────────────────────────────────
    testWidgets('golden onboarding_sign_in_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(0);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      await _openCreateAccount(tester);
      await tester.tap(find.byKey(const ValueKey('onboarding_toggle_mode')));
      await settle(tester);
      expect(find.text('Welcome back'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_sign_in_${b}_x1.0_glass')),
      );
    });

    // ── OTP (step 1, awaiting code) ──────────────────────────────────────────
    testWidgets('golden onboarding_otp_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(0);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      await _openCreateAccount(tester);
      await _fillCreateAccount(tester);
      await tester.tap(find.byKey(const ValueKey('onboarding_auth_continue')));
      await settle(tester);
      expect(
        find.byKey(const ValueKey('onboarding_otp_field')),
        findsOneWidget,
      );
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_otp_${b}_x1.0_glass')),
      );
    });

    // ── Plan chooser (step 2) ────────────────────────────────────────────────
    testWidgets('golden onboarding_plan_chooser_${b}_x1.0_glass', (
      tester,
    ) async {
      final (_, _, widget) = await _setup(2);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text('Choose your plan'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(
          goldenPath('onboarding_plan_chooser_${b}_x1.0_glass'),
        ),
      );
    });

    // ── Notifications (step 3) ───────────────────────────────────────────────
    testWidgets('golden onboarding_notifications_${b}_x1.0_glass', (
      tester,
    ) async {
      final (_, _, widget) = await _setup(3);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text('Know when Karmi replies'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(
          goldenPath('onboarding_notifications_${b}_x1.0_glass'),
        ),
      );
    });
  }

  // ── Create account — text scale 2.0 (overflow gate) ───────────────────────
  testWidgets(
    'golden onboarding_create_account_light_x2.0_glass — no overflow',
    (tester) async {
      final (_, _, widget) = await _setup(0);
      const env = Env(brightness: Brightness.light, textScale: 2.0);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      await _openCreateAccount(tester);
      expectNoOverflow(tester);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(
          goldenPath('onboarding_create_account_light_x2.0_glass'),
        ),
      );
    },
  );

  // ── Plan chooser — text scale 2.0 (overflow gate) ─────────────────────────
  testWidgets('golden onboarding_plan_chooser_light_x2.0_glass — no overflow', (
    tester,
  ) async {
    final (_, _, widget) = await _setup(2);
    const env = Env(brightness: Brightness.light, textScale: 2.0);
    await pumpHost(tester, widget, env: env, size: phoneSize);
    expect(find.text('Choose your plan'), findsOneWidget);
    expectNoOverflow(tester);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(goldenPath('onboarding_plan_chooser_light_x2.0_glass')),
    );
  });
}
