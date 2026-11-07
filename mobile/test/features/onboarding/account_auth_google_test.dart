import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/clerk_email_code_actions.dart';
import 'package:karmi_app/auth/google_sign_in_button.dart';
import 'package:karmi_app/features/onboarding/widgets/account_auth_step.dart';
import 'package:karmi_app/features/onboarding/widgets/pill_cta.dart';

import '../../support/fake_clerk_actions.dart';
import '../../support/harness.dart';

class DelayedFakeClerkActions extends FakeClerkEmailCodeActions {
  Completer<GoogleSignInResult>? googleCompleter;

  @override
  Future<GoogleSignInResult> signInWithGoogle() async {
    calls.add('signInWithGoogle');
    if (googleCompleter != null) {
      final result = await googleCompleter!.future;
      if (result is GoogleSignInSuccess) isSignedIn = true;
      return result;
    }
    return super.signInWithGoogle();
  }
}

Future<void> _pumpAuthStep(
  WidgetTester tester, {
  ClerkEmailCodeActions? actions,
  bool startInSignIn = false,
  void Function(AccountDetails?)? onSignedIn,
  Size size = const Size(480, 915),
}) async {
  await pumpHost(
    tester,
    AccountAuthStep(
      actions: actions,
      devAuthEnabled: false,
      totalSteps: 3,
      currentStep: 1,
      startInSignIn: startInSignIn,
      onBack: () {},
      onSignedIn: onSignedIn ?? (_) {},
      onDevSignIn: () async {},
    ),
    size: size,
  );
  await settle(tester);
}

void main() {
  group('AccountAuthStep Google sign-in flow', () {
    testWidgets('renders Google sign-in button in Create account mode', (
      tester,
    ) async {
      final fake = FakeClerkEmailCodeActions();
      await _pumpAuthStep(tester, actions: fake, startInSignIn: false);

      expect(find.text('Create your account'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('onboarding_google_button')),
        findsOneWidget,
      );
      expect(find.text('Continue with Google'), findsOneWidget);
      expect(find.text('or'), findsOneWidget);
    });

    testWidgets('renders Google sign-in button in Sign in mode', (
      tester,
    ) async {
      final fake = FakeClerkEmailCodeActions();
      await _pumpAuthStep(tester, actions: fake, startInSignIn: true);

      expect(find.text('Welcome back'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('onboarding_google_button')),
        findsOneWidget,
      );
      expect(find.text('Continue with Google'), findsOneWidget);
      expect(find.text('or'), findsOneWidget);
    });

    testWidgets('accessible semantics for Google sign-in button', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      final fake = FakeClerkEmailCodeActions();
      await _pumpAuthStep(tester, actions: fake);

      final finder = find.bySemanticsLabel(RegExp('Continue with Google'));
      expect(finder, findsOneWidget);

      final semantics = tester.getSemantics(finder);
      expect(semantics.flagsCollection.isButton, isTrue);
      expect(semantics.flagsCollection.isEnabled, ui.Tristate.isTrue);
      handle.dispose();
    });

    testWidgets(
      'tap triggers signInWithGoogle and invokes onSignedIn on success',
      (tester) async {
        final fake = FakeClerkEmailCodeActions();
        fake.nextGoogleResult = const GoogleSignInResult.success();

        AccountDetails? receivedDetails;
        var onSignedInCalled = false;

        await _pumpAuthStep(
          tester,
          actions: fake,
          startInSignIn: false,
          onSignedIn: (details) {
            onSignedInCalled = true;
            receivedDetails = details;
          },
        );

        // Fill in first name before tapping Google
        await tester.enterText(
          find.byKey(const ValueKey('onboarding_first_name_field')),
          'Ada',
        );
        await tester.pump();

        final googleButton = find.byKey(
          const ValueKey('onboarding_google_button'),
        );
        expect(googleButton, findsOneWidget);

        await tester.tap(googleButton);
        await settle(tester);

        expect(fake.calls, contains('signInWithGoogle'));
        expect(onSignedInCalled, isTrue);
        expect(receivedDetails, isNull);
      },
    );

    testWidgets(
      'tap in Sign in mode invokes onSignedIn with null details on success',
      (tester) async {
        final fake = FakeClerkEmailCodeActions();
        fake.nextGoogleResult = const GoogleSignInResult.success();

        AccountDetails? receivedDetails;
        var onSignedInCalled = false;

        await _pumpAuthStep(
          tester,
          actions: fake,
          startInSignIn: true,
          onSignedIn: (details) {
            onSignedInCalled = true;
            receivedDetails = details;
          },
        );

        final googleButton = find.byKey(
          const ValueKey('onboarding_google_button'),
        );
        await tester.tap(googleButton);
        await settle(tester);

        expect(fake.calls, contains('signInWithGoogle'));
        expect(onSignedInCalled, isTrue);
        expect(receivedDetails, isNull);
      },
    );

    testWidgets('loading state disables all auth actions and inputs', (
      tester,
    ) async {
      final fake = DelayedFakeClerkActions();
      final completer = Completer<GoogleSignInResult>();
      fake.googleCompleter = completer;

      await _pumpAuthStep(tester, actions: fake);

      final googleButtonFinder = find.byKey(
        const ValueKey('onboarding_google_button'),
      );
      final ctaFinder = find.byKey(const ValueKey('onboarding_auth_continue'));
      // Tapping initiates loading
      await tester.tap(googleButtonFinder);
      await tester.pump();

      // In-flight: Google button displays loading state
      final buttonWidget = tester.widget<GoogleSignInButton>(
        googleButtonFinder,
      );
      expect(buttonWidget.isLoading, isTrue);
      expect(buttonWidget.onPressed, isNull);

      // Form CTA button is in loading/disabled state while busy
      final ctaWidget = tester.widget<PillCta>(ctaFinder);
      expect(ctaWidget.isLoading, isTrue);
      final filledButton = tester.widget<FilledButton>(
        find.descendant(of: ctaFinder, matching: find.byType(FilledButton)),
      );
      expect(filledButton.onPressed, isNull);

      // Mode toggle and password input are also disabled
      final toggleWidget = tester.widget<TextButton>(
        find.byKey(const ValueKey('onboarding_toggle_mode')),
      );
      expect(toggleWidget.onPressed, isNull);
      final passwordWidget = tester.widget<TextField>(
        find.byKey(const ValueKey('onboarding_password_field')),
      );
      expect(passwordWidget.enabled, isFalse);
      // Second tap on Google button does not trigger duplicate call
      await tester.tap(googleButtonFinder, warnIfMissed: false);
      await tester.pump();
      expect(
        fake.calls.where((c) => c == 'signInWithGoogle').length,
        equals(1),
      );

      // Finish async work
      completer.complete(const GoogleSignInResult.success());
      await settle(tester);
    });

    testWidgets(
      'displays cancel message "Google sign-in was cancelled." when cancelled',
      (tester) async {
        final fake = FakeClerkEmailCodeActions();
        fake.nextGoogleResult = const GoogleSignInResult.cancelled();

        var onSignedInCalled = false;
        await _pumpAuthStep(
          tester,
          actions: fake,
          onSignedIn: (_) {
            onSignedInCalled = true;
          },
        );

        final googleButton = find.byKey(
          const ValueKey('onboarding_google_button'),
        );
        await tester.tap(googleButton);
        await settle(tester);

        expect(fake.calls, contains('signInWithGoogle'));
        expect(onSignedInCalled, isFalse);

        // Cancel message is shown in the form error section
        expect(find.text('Google sign-in was cancelled.'), findsOneWidget);

        // Form remains interactive
        final buttonWidget = tester.widget<GoogleSignInButton>(googleButton);
        expect(buttonWidget.isLoading, isFalse);
        expect(buttonWidget.onPressed, isNotNull);
      },
    );

    testWidgets('displays error message and form stays usable on error', (
      tester,
    ) async {
      final fake = FakeClerkEmailCodeActions();
      fake.nextGoogleResult = const GoogleSignInResult.error(
        'Google OAuth identity provider was unreachable.',
      );

      await _pumpAuthStep(tester, actions: fake);

      final googleButton = find.byKey(
        const ValueKey('onboarding_google_button'),
      );
      await tester.tap(googleButton);
      await settle(tester);

      expect(
        find.text('Google OAuth identity provider was unreachable.'),
        findsOneWidget,
      );

      // Form inputs and buttons remain usable after error
      final buttonWidget = tester.widget<GoogleSignInButton>(googleButton);
      expect(buttonWidget.isLoading, isFalse);
      expect(buttonWidget.onPressed, isNotNull);

      final ctaWidget = tester.widget<PillCta>(
        find.byKey(const ValueKey('onboarding_auth_continue')),
      );
      expect(ctaWidget.onPressed, isNotNull);
      final passwordWidget = tester.widget<TextField>(
        find.byKey(const ValueKey('onboarding_password_field')),
      );
      expect(passwordWidget.enabled, isTrue);
    });

    testWidgets(
      'Google sign-in start failure displays retry message and re-enables actions',
      (tester) async {
        final fake = FakeClerkEmailCodeActions();
        fake.nextGoogleResult = const GoogleSignInError(
          'Google sign-in could not start. Please try again.',
        );

        await _pumpAuthStep(tester, actions: fake);

        final googleButton = find.byKey(
          const ValueKey('onboarding_google_button'),
        );
        await tester.tap(googleButton);
        await settle(tester);

        expect(fake.calls, contains('signInWithGoogle'));
        expect(
          find.text('Google sign-in could not start. Please try again.'),
          findsOneWidget,
        );

        // Actions and form remain interactive
        final buttonWidget = tester.widget<GoogleSignInButton>(googleButton);
        expect(buttonWidget.isLoading, isFalse);
        expect(buttonWidget.onPressed, isNotNull);

        final ctaWidget = tester.widget<PillCta>(
          find.byKey(const ValueKey('onboarding_auth_continue')),
        );
        expect(ctaWidget.isLoading, isFalse);
        expect(ctaWidget.onPressed, isNotNull);

        final passwordWidget = tester.widget<TextField>(
          find.byKey(const ValueKey('onboarding_password_field')),
        );
        expect(passwordWidget.enabled, isTrue);
      },
    );

    testWidgets(
      'Google sign-in transfer with missing fields surfaces required fields error',
      (tester) async {
        final fake = FakeClerkEmailCodeActions();
        fake.nextGoogleResult = const GoogleSignInError(
          'Clerk still needs: username.',
        );

        await _pumpAuthStep(tester, actions: fake);

        final googleButton = find.byKey(
          const ValueKey('onboarding_google_button'),
        );
        await tester.tap(googleButton);
        await settle(tester);

        expect(fake.calls, contains('signInWithGoogle'));
        expect(find.text('Clerk still needs: username.'), findsOneWidget);

        // Form remains interactive and re-enabled
        final buttonWidget = tester.widget<GoogleSignInButton>(googleButton);
        expect(buttonWidget.isLoading, isFalse);
        expect(buttonWidget.onPressed, isNotNull);

        final ctaWidget = tester.widget<PillCta>(
          find.byKey(const ValueKey('onboarding_auth_continue')),
        );
        expect(ctaWidget.isLoading, isFalse);
        expect(ctaWidget.onPressed, isNotNull);
      },
    );
    testWidgets('hidden when actions is null (Clerk not configured)', (
      tester,
    ) async {
      await _pumpAuthStep(tester, actions: null);

      expect(
        find.byKey(const ValueKey('onboarding_google_button')),
        findsNothing,
      );
      expect(find.text('Continue with Google'), findsNothing);
      expect(find.text('or'), findsNothing);
    });

    testWidgets('hidden when actions.isNotAvailable is true', (tester) async {
      final fake = FakeClerkEmailCodeActions();
      fake.isNotAvailable = true;

      await _pumpAuthStep(tester, actions: fake);

      expect(
        find.byKey(const ValueKey('onboarding_google_button')),
        findsNothing,
      );
      expect(find.text('Continue with Google'), findsNothing);
      expect(find.text('or'), findsNothing);
    });
  });
}
