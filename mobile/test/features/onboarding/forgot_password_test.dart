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

const _forgot = ValueKey('onboarding_forgot_password');
const _resetEmail = ValueKey('onboarding_reset_email_field');
const _resetOtp = ValueKey('onboarding_reset_otp_field');
const _newPassword = ValueKey('onboarding_reset_new_password_field');
const _confirmPassword = ValueKey('onboarding_reset_confirm_password_field');
const _resetBack = ValueKey('onboarding_reset_back');
const _resetResend = ValueKey('onboarding_reset_resend_code');

Future<void> _pumpFlow(
  WidgetTester tester, {
  required FakeClerkEmailCodeActions fake,
}) async {
  SharedPreferences.setMockInitialValues({'onboarding_active_step': 1});
  final prefs = await SharedPreferences.getInstance();
  final settings = KarmiSettings(prefs);
  final session = KarmiSession(
    api: KarmiApi(
      baseUrl: 'http://karmi.test',
      client: FakeBackend.healthy().client,
    ),
    prefs: prefs,
  );
  await pumpHost(
    tester,
    OnboardingFlow(
      session: session,
      settings: settings,
      clerkActions: fake,
      devAuthEnabled: false,
    ),
  );
  await settle(tester);
}

Future<void> _openSignIn(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('onboarding_toggle_mode')));
  await settle(tester);
}

Future<void> _tapCta(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('onboarding_auth_continue')));
  await settle(tester);
}

Future<void> _enter(WidgetTester tester, Key key, String text) =>
    tester.enterText(find.byKey(key), text);

/// Opens the reset form from sign-in with [typed] in the email field.
Future<void> _openReset(WidgetTester tester, {String typed = ''}) async {
  await _openSignIn(tester);
  if (typed.isNotEmpty) {
    await _enter(tester, const ValueKey('onboarding_email_field'), typed);
  }
  await tester.tap(find.byKey(_forgot));
  await settle(tester);
}

/// Sends the reset code and lands on the code + new password step.
Future<void> _toCodeStep(WidgetTester tester) async {
  await _openReset(tester, typed: 'alice@example.com');
  await _tapCta(tester);
  expect(find.byKey(_resetOtp), findsOneWidget);
}

Future<void> _fillReset(
  WidgetTester tester, {
  String code = '123456',
  String password = 'Sunrise#42',
  String? confirm,
}) async {
  await _enter(tester, _resetOtp, code);
  await _enter(tester, _newPassword, password);
  await _enter(tester, _confirmPassword, confirm ?? password);
}

void main() {
  testWidgets('Forgot password? shows in sign-in mode only', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);

    expect(find.text('Create your account'), findsOneWidget);
    expect(find.byKey(_forgot), findsNothing);

    await _openSignIn(tester);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.byKey(_forgot), findsOneWidget);
    expect(find.text('Forgot password?'), findsOneWidget);
  });

  testWidgets('email step prefills from sign-in and sends the trimmed email', (
    tester,
  ) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _openReset(tester, typed: '  alice@example.com  ');

    expect(find.text('Reset your password'), findsOneWidget);
    expect(find.text('Send reset code'), findsOneWidget);
    final field = tester.widget<TextField>(find.byKey(_resetEmail));
    expect(field.controller!.text.trim(), 'alice@example.com');

    await _tapCta(tester);

    expect(fake.calls, ['startPasswordReset']);
    expect(fake.lastResetEmail, 'alice@example.com');
    expect(find.text('Choose a new password'), findsOneWidget);
    expect(find.text('Reset password'), findsOneWidget);
  });

  testWidgets('empty or invalid email blocks sending', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _openReset(tester);

    await _tapCta(tester);
    expect(find.text('Enter a valid email address.'), findsOneWidget);

    await _enter(tester, _resetEmail, 'alice_k');
    await _tapCta(tester);
    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(fake.calls, isEmpty);
    expect(find.byKey(_resetOtp), findsNothing);
  });

  for (final code in [
    'form_identifier_not_found',
    'strategy_for_user_invalid',
  ]) {
    testWidgets('$code looks like a sent code and never signs in', (
      tester,
    ) async {
      final fake = FakeClerkEmailCodeActions()
        ..nextError = clerkErrorWithCodes([code]);
      await _pumpFlow(tester, fake: fake);
      await _openReset(tester, typed: 'nobody@example.com');
      await _tapCta(tester);

      // Same screen and copy as a real send; nothing says "no account".
      expect(find.byKey(_resetOtp), findsOneWidget);
      expect(find.textContaining('If an account exists'), findsOneWidget);
      expect(find.textContaining('No account found'), findsNothing);
      expect(
        find.byKey(const ValueKey('onboarding_offer_create')),
        findsNothing,
      );

      await _fillReset(tester);
      await _tapCta(tester);

      // Fails like a wrong code, without calling Clerk again.
      expect(find.text('Code is incorrect or expired.'), findsOneWidget);
      expect(fake.calls, ['startPasswordReset']);
      expect(fake.isSignedIn, isFalse);
    });
  }

  testWidgets('password rule failures and mismatch block the reset', (
    tester,
  ) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _toCodeStep(tester);

    await _fillReset(tester, code: '12', password: 'short', confirm: 'other');
    await _tapCta(tester);

    expect(find.text('Enter the 6-digit code.'), findsOneWidget);
    expect(
      find.text(
        'Password needs at least 8 characters, an uppercase letter, a number, a special character.',
      ),
      findsOneWidget,
    );
    expect(find.text('Passwords do not match.'), findsOneWidget);
    expect(fake.calls, ['startPasswordReset']);

    // Valid rules but mismatching confirmation.
    await _fillReset(tester, confirm: 'Sunrise#43');
    await _tapCta(tester);
    expect(find.text('Passwords do not match.'), findsOneWidget);
    expect(fake.calls, ['startPasswordReset']);
  });

  testWidgets('successful reset passes code and password and signs in', (
    tester,
  ) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _toCodeStep(tester);

    await _fillReset(tester);
    await _tapCta(tester);

    expect(fake.calls, ['startPasswordReset', 'completePasswordReset']);
    expect(fake.lastResetCode, '123456');
    expect(fake.lastResetPassword, 'Sunrise#42');
    expect(fake.isSignedIn, isTrue);
    expect(find.text('Choose your plan'), findsOneWidget);
  });

  testWidgets('reset that needs a second factor reuses the email code step', (
    tester,
  ) async {
    final fake = FakeClerkEmailCodeActions()..resetRequiresSecondFactor = true;
    await _pumpFlow(tester, fake: fake);
    await _toCodeStep(tester);

    await _fillReset(tester);
    await _tapCta(tester);

    expect(fake.calls, [
      'startPasswordReset',
      'completePasswordReset',
      'sendSignInCode',
    ]);
    expect(find.text('Enter verification code'), findsOneWidget);
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsOneWidget);
    expect(find.byKey(_resetOtp), findsNothing);

    await _enter(tester, const ValueKey('onboarding_otp_field'), '424242');
    await _tapCta(tester);
    expect(fake.calls.last, 'verifySignIn');
    expect(find.text('Choose your plan'), findsOneWidget);
  });

  testWidgets('incorrect code error appears under the code field', (
    tester,
  ) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _toCodeStep(tester);

    fake.nextError = clerkErrorWithCodes(['form_code_incorrect']);
    await _fillReset(tester);
    await _tapCta(tester);

    expect(find.text('Code is incorrect or expired.'), findsOneWidget);
    expect(find.byKey(_resetOtp), findsOneWidget);
    expect(find.text('What should we call you?'), findsNothing);
  });

  testWidgets('breached password error appears under the new password field', (
    tester,
  ) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _toCodeStep(tester);

    fake.nextError = clerkErrorWithCodes(['form_password_pwned']);
    await _fillReset(tester);
    await _tapCta(tester);

    expect(
      find.text(
        'This password appears in a known data breach. Choose a different one.',
      ),
      findsOneWidget,
    );
    expect(fake.isSignedIn, isFalse);
  });

  testWidgets('resend is disabled during the cooldown', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    await _toCodeStep(tester);

    final resend = tester.widget<TextButton>(find.byKey(_resetResend));
    expect(resend.onPressed, isNull);
    expect(find.textContaining('Resend in'), findsOneWidget);

    await tester.pump(const Duration(seconds: 31));
    final enabled = tester.widget<TextButton>(find.byKey(_resetResend));
    expect(enabled.onPressed, isNotNull);
    await tester.tap(find.byKey(_resetResend));
    await settle(tester);
    expect(fake.calls, ['startPasswordReset', 'startPasswordReset']);
  });

  testWidgets('Back to sign in resets the form at every step', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);

    // Email step.
    await _openReset(tester, typed: 'alice@example.com');
    await tester.tap(find.byKey(_resetBack));
    await settle(tester);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.byKey(_resetEmail), findsNothing);

    // Code step: typed values do not survive a second visit.
    await tester.tap(find.byKey(_forgot));
    await settle(tester);
    await _tapCta(tester);
    await _fillReset(tester, password: 'Sunrise#42', confirm: 'nope');
    await _tapCta(tester);
    expect(find.text('Passwords do not match.'), findsOneWidget);
    await tester.tap(find.byKey(_resetBack));
    await settle(tester);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.text('Passwords do not match.'), findsNothing);

    await tester.tap(find.byKey(_forgot));
    await settle(tester);
    await _tapCta(tester);
    final password = tester.widget<TextField>(find.byKey(_newPassword));
    expect(password.controller!.text, isEmpty);
    final code = tester.widget<TextField>(
      find.descendant(
        of: find.byKey(_resetOtp),
        matching: find.byType(TextField),
      ),
    );
    expect(code.controller!.text, isEmpty);
  });
}
