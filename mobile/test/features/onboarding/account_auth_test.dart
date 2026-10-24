import 'package:clerk_auth/clerk_auth.dart' as clerk;
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

clerk.ClerkError _clerkError(String code) => clerkErrorWithCodes([code]);

/// Pumps the onboarding flow at [step] with [fake] standing in for Clerk.
/// Pass [backend] to route API calls; a signed-in session is created when
/// [signedIn] is true.
Future<void> _pumpFlow(
  WidgetTester tester, {
  required FakeClerkEmailCodeActions fake,
  int step = 1,
  bool signedIn = false,
  FakeBackend? backend,
}) async {
  SharedPreferences.setMockInitialValues({'onboarding_active_step': step});
  final prefs = await SharedPreferences.getInstance();
  final settings = KarmiSettings(prefs);
  final net = backend ?? FakeBackend.healthy();
  final session = KarmiSession(
    api: KarmiApi(baseUrl: 'http://karmi.test', client: net.client),
    prefs: prefs,
  );
  if (signedIn) await session.signInWithDevToken();
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

Future<void> _fillCreateForm(
  WidgetTester tester, {
  String password = 'Sunrise#42',
  String email = 'alice@example.com',
}) async {
  await tester.enterText(find.byKey(const ValueKey('onboarding_first_name_field')), 'Alice');
  await tester.enterText(find.byKey(const ValueKey('onboarding_username_field')), 'alice_k');
  await tester.enterText(find.byKey(const ValueKey('onboarding_email_field')), email);
  await tester.enterText(find.byKey(const ValueKey('onboarding_password_field')), password);
}

Future<void> _tapCta(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('onboarding_auth_continue')));
  await settle(tester);
}

/// Lets async fake-Clerk work finish without advancing the fake clock, so
/// cooldown assertions see exactly the ticks the test pumps.
Future<void> _settleNoClock(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
  }
}

Future<void> _tapNoClock(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('onboarding_auth_continue')));
  await _settleNoClock(tester);
}

void main() {
  testWidgets('create-account validation errors show inline and nothing is sent', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);
    expect(find.text('Create your account'), findsOneWidget);

    await _fillCreateForm(tester, email: 'not-an-email', password: 'short');
    await tester.enterText(find.byKey(const ValueKey('onboarding_username_field')), 'ab');
    await _tapCta(tester);

    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(find.text('Use 4–64 letters, numbers, _ or -.'), findsOneWidget);
    expect(
      find.text(
        'Password needs at least 8 characters, an uppercase letter, a number, a special character.',
      ),
      findsOneWidget,
    );
    expect(fake.calls, isEmpty);
  });

  testWidgets('empty first name shows the form-level error and sends nothing', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);

    await _fillCreateForm(tester);
    await tester.enterText(find.byKey(const ValueKey('onboarding_first_name_field')), ' ');
    await _tapCta(tester);

    expect(find.text('First name must be at least 2 characters.'), findsOneWidget);
    expect(fake.calls, isEmpty);
  });

  testWidgets('identifier exists on sign-up offers Sign in', (tester) async {
    final fake = FakeClerkEmailCodeActions()
      ..nextError = _clerkError('form_identifier_exists');
    await _pumpFlow(tester, fake: fake);

    await _fillCreateForm(tester);
    await _tapCta(tester);

    expect(
      find.text('An account already exists for this email. Sign in instead.'),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('onboarding_offer_sign_in')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('onboarding_offer_sign_in')));
    await settle(tester);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.byKey(const ValueKey('onboarding_password_field')), findsOneWidget);
  });

  testWidgets('pwned password on sign-up is shown on the password field', (tester) async {
    final fake = FakeClerkEmailCodeActions()
      ..nextError = _clerkError('form_password_pwned');
    await _pumpFlow(tester, fake: fake);

    await _fillCreateForm(tester);
    await _tapCta(tester);

    expect(fake.calls, ['signUp']);
    expect(
      find.text(
        'This password appears in a known data breach. Choose a different one.',
      ),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsNothing);
  });

  testWidgets('sign-in with password completes and advances to the profile step', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);

    await tester.tap(find.byKey(const ValueKey('onboarding_toggle_mode')));
    await settle(tester);
    expect(find.text('Welcome back'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('onboarding_email_field')), 'alice_k');
    await tester.enterText(find.byKey(const ValueKey('onboarding_password_field')), 'Sunrise#42');
    await _tapCta(tester);

    expect(fake.calls, ['signIn']);
    expect(fake.lastSignInIdentifier, 'alice_k');
    expect(fake.lastPassword, 'Sunrise#42');
    expect(find.text('What should we call you?'), findsOneWidget);
  });

  testWidgets('sign-in that needs an email code shows the OTP field', (tester) async {
    final fake = FakeClerkEmailCodeActions()..requireSecondFactor = true;
    await _pumpFlow(tester, fake: fake);

    await tester.tap(find.byKey(const ValueKey('onboarding_toggle_mode')));
    await settle(tester);
    await tester.enterText(find.byKey(const ValueKey('onboarding_email_field')), 'alice@example.com');
    await tester.enterText(find.byKey(const ValueKey('onboarding_password_field')), 'Sunrise#42');
    await _tapCta(tester);

    expect(find.text('Enter verification code'), findsOneWidget);
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsOneWidget);
    expect(find.text('Verify & Continue'), findsOneWidget);
    expect(find.text('What should we call you?'), findsNothing);
  });

  testWidgets('resend is disabled during the 30 second cooldown, then re-enabled', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);

    await _fillCreateForm(tester);
    await _tapNoClock(tester);
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsOneWidget);
    expect(find.text('Resend in 30s'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('onboarding_resend_code')));
    await _settleNoClock(tester);
    expect(fake.calls, ['signUp'], reason: 'resend is ignored during cooldown');

    for (var i = 0; i < 29; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(find.text('Resend in 1s'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Resend code'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('onboarding_resend_code')));
    await _settleNoClock(tester);
    expect(fake.calls, ['signUp', 'resend']);
    expect(find.text('Resend in 30s'), findsOneWidget);
  });

  testWidgets('back from the OTP screen returns to editable details', (tester) async {
    final fake = FakeClerkEmailCodeActions();
    await _pumpFlow(tester, fake: fake);

    await _fillCreateForm(tester);
    await _tapCta(tester);
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('onboarding_change_details')));
    await settle(tester);
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsNothing);
    expect(find.text('Create your account'), findsOneWidget);

    final email = tester.widget<TextField>(
      find.byKey(const ValueKey('onboarding_email_field')),
    );
    expect(email.controller!.text, 'alice@example.com');

    await tester.enterText(
      find.byKey(const ValueKey('onboarding_email_field')),
      'alice2@example.com',
    );
    await _tapCta(tester);
    expect(fake.calls, ['signUp', 'signUp']);
    expect(fake.lastSignUpUsername, 'alice_k');
    expect(find.byKey(const ValueKey('onboarding_otp_field')), findsOneWidget);
  });

  testWidgets('profile save backend error is shown and does not advance', (tester) async {
    // Signed-in session; PATCH /v1/user/profile is unrouted, so it fails.
    final fake = FakeClerkEmailCodeActions();
    final backend = FakeBackend()
      ..on('POST', '/dev/token', (_) => jsonResponse({'token': 't', 'user_id': 'u'}));
    await _pumpFlow(tester, fake: fake, step: 2, signedIn: true, backend: backend);
    expect(find.text('What should we call you?'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('onboarding_first_name_field')),
      'Alice',
    );
    await tester.tap(find.byKey(const ValueKey('onboarding_profile_continue')));
    await settle(tester);

    expect(
      find.text('Could not save your name. Check your connection and try again.'),
      findsOneWidget,
    );
    expect(find.text('What should we call you?'), findsOneWidget);
    expect(find.text('Choose your model approach'), findsNothing);
  });
}
