import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/clerk_email_code_actions.dart';
import 'package:karmi_app/auth/clerk_sign_in_card.dart';

import '../support/harness.dart';

void main() {
  testWidgets('email sign-in requests a code and completes verification', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions();
    await pumpHost(tester, ClerkSignInCard(actions: actions));

    await tester.enterText(find.byType(TextField).first, 'person@example.com');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(actions.signInCalls, 1);
    expect(find.text('Check your email'), findsOneWidget);
    expect(find.textContaining('person@example.com'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, '123456');
    await tester.tap(find.text('Verify and continue'));
    await tester.pumpAndSettle();
    expect(actions.signInCalls, 2);
    expect(actions.isSignedIn, isTrue);
    expect(find.text('Welcome back'), findsNothing);
  });

  testWidgets(
    'sign-up supports required names, code resend, and verification',
    (tester) async {
      final actions = FakeClerkEmailCodeActions()..requireFirstName = true;
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.tap(find.text('New to Karmi? Create an account'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'new@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        'password123',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        'password123',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(find.text('First name (required)'), findsOneWidget);
      expect(
        find.text('Complete the required account details, then continue.'),
        findsOneWidget,
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'First name (required)'),
        'New',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(actions.signUpCalls, 2);
      expect(find.text('Check your email'), findsOneWidget);

      await tester.tap(find.text('Resend code'));
      await tester.pumpAndSettle();
      expect(actions.resendCalls, 1);
      expect(find.text('A new verification code was sent.'), findsOneWidget);
      await tester.enterText(find.byType(TextField).last, '123456');
      await tester.tap(find.text('Verify and continue'));
      await tester.pumpAndSettle();
      expect(actions.isSignedIn, isTrue);
    },
  );

  testWidgets('Clerk errors are shown in the Karmi form', (tester) async {
    final actions = FakeClerkEmailCodeActions()
      ..nextError = 'Email code rejected';
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.enterText(find.byType(TextField).first, 'person@example.com');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Email code rejected'), findsOneWidget);
  });

  testWidgets('sign-up fails closed when legal consent is required', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions()..legalConsentRequired = true;
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.tap(find.text('New to Karmi? Create an account'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Email address'),
      'new@example.com',
    );
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(actions.signUpCalls, 0);
    expect(
      find.textContaining('terms and privacy consent are configured'),
      findsOneWidget,
    );
  });

  test('unsupported required Clerk fields are identified explicitly', () {
    expect(
      unsupportedClerkSignUpFields([
        clerk.Field.emailAddress,
        clerk.Field.firstName,
        clerk.Field.lastName,
      ]),
      isEmpty,
    );
    expect(
      unsupportedClerkSignUpFields([
        clerk.Field.password,
        clerk.Field.phoneNumber,
      ]),
      ['phone_number'],
    );
  });

  testWidgets('password fields render on Create account with obscureText', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions();
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.tap(find.text('New to Karmi? Create an account'));
    await tester.pumpAndSettle();

    final passwordFieldFinder = find.widgetWithText(
      TextField,
      'Create a password',
    );
    final confirmFieldFinder = find.widgetWithText(
      TextField,
      'Confirm password',
    );
    expect(passwordFieldFinder, findsOneWidget);
    expect(confirmFieldFinder, findsOneWidget);

    final passwordWidget = tester.widget<TextField>(passwordFieldFinder);
    final confirmWidget = tester.widget<TextField>(confirmFieldFinder);
    expect(passwordWidget.obscureText, isTrue);
    expect(passwordWidget.autofillHints, contains(AutofillHints.newPassword));
    expect(confirmWidget.obscureText, isTrue);
    expect(confirmWidget.autofillHints, contains(AutofillHints.newPassword));
  });

  testWidgets('mismatch and <8 chars block submission with a visible error', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions();
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.tap(find.text('New to Karmi? Create an account'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Email address'),
      'person@example.com',
    );

    // Less than 8 chars
    await tester.enterText(
      find.widgetWithText(TextField, 'Create a password'),
      'short',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Confirm password'),
      'short',
    );
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(actions.signUpCalls, 0);
    expect(
      find.text('Password must be at least 8 characters.'),
      findsOneWidget,
    );

    // Mismatch
    await tester.enterText(
      find.widgetWithText(TextField, 'Create a password'),
      'password123',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Confirm password'),
      'password456',
    );
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(actions.signUpCalls, 0);
    expect(find.text('Passwords do not match.'), findsOneWidget);
  });

  testWidgets(
    'attemptSignUp receives password and confirmation',
    (tester) async {
      final actions = FakeClerkEmailCodeActions();
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.tap(find.text('New to Karmi? Create an account'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'user@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        'supersecret123',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        'supersecret123',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 1);
      expect(actions.lastPassword, 'supersecret123');
      expect(actions.lastPasswordConfirmation, 'supersecret123');
    },
  );

  testWidgets(
    'mid sign-up resume shows password fields and completes sign-up',
    (tester) async {
      final actions = FakeClerkEmailCodeActions()
        ..isMidSignUp = true
        ..signUpEmail = 'resume@example.com';
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.pumpAndSettle();

      expect(
        find.widgetWithText(TextField, 'Create a password'),
        findsOneWidget,
      );
      expect(
        find.widgetWithText(TextField, 'Confirm password'),
        findsOneWidget,
      );
      expect(find.text('resume@example.com'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        'resumepass123',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        'resumepass123',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 1);
      expect(actions.lastPassword, 'resumepass123');
      expect(actions.lastPasswordConfirmation, 'resumepass123');
      expect(actions.isSignedIn, isTrue);
    },
  );
}

class FakeClerkEmailCodeActions implements ClerkEmailCodeActions {
  @override
  bool isSignedIn = false;
  @override
  bool isNotAvailable = false;
  @override
  bool supportsEmailCode = true;
  @override
  bool legalConsentRequired = false;
  @override
  bool isMidSignUp = false;
  @override
  String? signUpEmail;
  bool requireFirstName = false;
  String? nextError;
  bool _signInAwaitingCode = false;
  bool _signUpAwaitingCode = false;
  final List<clerk.Field> _missing = [];
  int signInCalls = 0;
  int signUpCalls = 0;
  int resendCalls = 0;
  String? lastPassword;
  String? lastPasswordConfirmation;
  @override
  bool get signInAwaitingCode => _signInAwaitingCode;

  @override
  bool get signUpAwaitingCode => _signUpAwaitingCode;

  @override
  List<clerk.Field> get signUpMissingFields => List.unmodifiable(_missing);

  void _error(ClerkFlowErrorHandler onError) {
    final error = nextError;
    if (error != null) {
      nextError = null;
      onError(error);
    }
  }

  @override
  Future<void> signIn(
    String email,
    String? code,
    ClerkFlowErrorHandler onError,
  ) async {
    signInCalls++;
    if (nextError != null) return _error(onError);
    if (code == null) {
      _signInAwaitingCode = true;
    } else {
      _signInAwaitingCode = false;
      isSignedIn = true;
    }
  }

  @override
  Future<void> signUp(
    String email,
    String? firstName,
    String? lastName,
    String? code,
    ClerkFlowErrorHandler onError, {
    String? password,
    String? passwordConfirmation,
  }) async {
    signUpCalls++;
    lastPassword = password;
    lastPasswordConfirmation = passwordConfirmation;
    if (nextError != null) return _error(onError);
    _missing
      ..clear()
      ..addAll(
        requireFirstName && (firstName?.isNotEmpty != true)
            ? [clerk.Field.firstName]
            : [],
      );
    if (_missing.isNotEmpty) return;
    if (isMidSignUp) {
      isMidSignUp = false;
      isSignedIn = true;
      return;
    }
    if (code == null) {
      _signUpAwaitingCode = true;
    } else {
      _signUpAwaitingCode = false;
      isSignedIn = true;
    }
  }

  @override
  Future<void> resendCode(ClerkFlowErrorHandler onError) async {
    resendCalls++;
    _error(onError);
  }

  @override
  Future<void> reset(ClerkFlowErrorHandler onError) async {
    _signInAwaitingCode = false;
    _signUpAwaitingCode = false;
    _error(onError);
  }
}
