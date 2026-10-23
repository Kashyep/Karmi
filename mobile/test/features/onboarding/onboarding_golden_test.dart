/// Comprehensive golden tests for every onboarding screen.
///
/// Screens covered (light + dark, x1.0 glass):
///   welcome, auth, otp, name, preferences, plan_intro, notifications, completion
///
/// Extra cases:
///   name_error  — name step with validation error showing
///   name_x2.0   — name step at text scale 2.0 (overflow gate)
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/onboarding/onboarding.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fake_backend.dart';
import '../../support/harness.dart';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Builds a session+settings starting at [step] and returns the golden-ready
/// [OnboardingFlow] widget.
Future<(KarmiSettings, KarmiSession, OnboardingFlow)> _setup(
  int step, {
  bool devAuthEnabled = false,
}) async {
  SharedPreferences.setMockInitialValues(
    step > 0 ? {'onboarding_active_step': step} : {},
  );
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
  );
  return (settings, session, widget);
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

    // ── Auth — email entry (step 1) ─────────────────────────────────────────
    testWidgets('golden onboarding_auth_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(0, devAuthEnabled: false);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      await tester.tap(find.text('Get Started'));
      await settle(tester);
      expect(find.text("What's your email?"), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_auth_${b}_x1.0_glass')),
      );
    });

    // ── OTP (step 1, awaiting code) ──────────────────────────────────────────
    testWidgets('golden onboarding_otp_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(0, devAuthEnabled: false);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      // Navigate to auth step
      await tester.tap(find.text('Get Started'));
      await settle(tester);
      // Enter a valid email and submit to reach OTP screen
      await tester.enterText(
        find.byKey(const ValueKey('onboarding_email_field')),
        'test@example.com',
      );
      await tester.tap(find.byKey(const ValueKey('onboarding_auth_continue')));
      await settle(tester);
      // The OTP field should now be visible (auth step transitions to awaiting-code state)
      expect(find.byKey(const ValueKey('onboarding_otp_field')), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_otp_${b}_x1.0_glass')),
      );
    });

    // ── Name (step 2) ────────────────────────────────────────────────────────
    testWidgets('golden onboarding_name_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(2);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text('What should we call you?'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_name_${b}_x1.0_glass')),
      );
    });

    // ── Name — error state ───────────────────────────────────────────────────
    testWidgets('golden onboarding_name_error_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(2);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      // Tap Continue without entering a name to trigger validation error
      await tester.tap(find.byKey(const ValueKey('onboarding_profile_continue')));
      await settle(tester);
      expect(
        find.text('First name must be at least 2 characters.'),
        findsOneWidget,
      );
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_name_error_${b}_x1.0_glass')),
      );
    });

    // ── Preferences (step 3) ─────────────────────────────────────────────────
    testWidgets('golden onboarding_preferences_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(3);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text('Set your preferences'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_preferences_${b}_x1.0_glass')),
      );
    });

    // ── Plan intro (step 4) ──────────────────────────────────────────────────
    testWidgets('golden onboarding_plan_intro_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(4);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text("You're starting on Ananta Free"), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_plan_intro_${b}_x1.0_glass')),
      );
    });

    // ── Notifications (step 5) ───────────────────────────────────────────────
    testWidgets('golden onboarding_notifications_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(5);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text('Stay updated on background tasks'), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(
          goldenPath('onboarding_notifications_${b}_x1.0_glass'),
        ),
      );
    });

    // ── Completion (step 6) ──────────────────────────────────────────────────
    testWidgets('golden onboarding_completion_${b}_x1.0_glass', (tester) async {
      final (_, _, widget) = await _setup(6);
      final env = Env(brightness: brightness);
      await pumpHost(tester, widget, env: env, size: phoneSize);
      expect(find.text("You're all set!"), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile(goldenPath('onboarding_completion_${b}_x1.0_glass')),
      );
    });
  }

  // ── Name screen — text scale 2.0 (overflow gate) ──────────────────────────
  testWidgets('golden onboarding_name_light_x2.0_glass — no overflow', (tester) async {
    final (_, _, widget) = await _setup(2);
    const env = Env(brightness: Brightness.light, textScale: 2.0);
    await pumpHost(tester, widget, env: env, size: phoneSize);
    expect(find.text('What should we call you?'), findsOneWidget);
    expectNoOverflow(tester);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(goldenPath('onboarding_name_light_x2.0_glass')),
    );
  });
}
