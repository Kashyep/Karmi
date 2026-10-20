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
    expect(
      find.text('Use the newest email; earlier codes no longer work.'),
      findsOneWidget,
    );
    expect(find.textContaining('person@example.com'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, '123456');
    await tester.tap(find.text('Verify and continue'));
    await tester.pumpAndSettle();
    expect(actions.verifySignInCalls, 1);
    expect(actions.lastVerifiedSignInCode, '123456');
    expect(actions.isSignedIn, isTrue);
    expect(find.text('Welcome back'), findsNothing);
  });

  testWidgets(
    'sign-up supports required names, code resend, and verification',
    (tester) async {
      final actions = FakeClerkEmailCodeActions()
        ..firstNameRequired = false
        ..lastNameRequired = false
        ..passwordMinLength = 8
        ..requireFirstName = true;
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
      expect(
        find.text('Use the newest email; earlier codes no longer work.'),
        findsOneWidget,
      );

      await tester.tap(find.text('Resend code'));
      await tester.pumpAndSettle();
      expect(actions.resendCalls, 1);
      expect(
        find.text('Use the newest email; earlier codes no longer work.'),
        findsOneWidget,
      );
      await tester.enterText(find.byType(TextField).last, '123456');
      await tester.tap(find.text('Verify and continue'));
      await tester.pumpAndSettle();
      expect(actions.verifySignUpCalls, 1);
      expect(actions.lastVerifiedSignUpCode, '123456');
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
    final actions = FakeClerkEmailCodeActions()
      ..firstNameRequired = false
      ..lastNameRequired = false
      ..passwordMinLength = 8;
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

  testWidgets('attemptSignUp receives password and confirmation', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions()
      ..firstNameRequired = false
      ..lastNameRequired = false
      ..passwordMinLength = 8;
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
  });

  testWidgets(
    'mid sign-up resume shows password fields and completes sign-up',
    (tester) async {
      final actions = FakeClerkEmailCodeActions()
        ..firstNameRequired = false
        ..lastNameRequired = false
        ..passwordMinLength = 8
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
  testWidgets(
    'code step on sign-up calls verifySignUpCode with code only and never passes password or name',
    (tester) async {
      final actions = FakeClerkEmailCodeActions()
        ..firstNameRequired = false
        ..lastNameRequired = false;
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.tap(find.text('New to Karmi? Create an account'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'user@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        'secretpassword123',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        'secretpassword123',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 1);
      expect(actions.lastPassword, 'secretpassword123');

      actions.lastPassword = null;
      actions.lastPasswordConfirmation = null;
      final signUpCallsBeforeVerify = actions.signUpCalls;

      await tester.enterText(
        find.widgetWithText(TextField, 'Verification code'),
        '654321',
      );
      await tester.tap(find.text('Verify and continue'));
      await tester.pumpAndSettle();

      expect(actions.verifySignUpCalls, 1);
      expect(actions.lastVerifiedSignUpCode, '654321');
      expect(actions.signUpCalls, signUpCallsBeforeVerify);
      expect(actions.lastPassword, isNull);
      expect(actions.lastPasswordConfirmation, isNull);
      expect(actions.isSignedIn, isTrue);
    },
  );

  testWidgets('a code-step submit never triggers resend or prepare', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions();
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.enterText(find.byType(TextField).first, 'user@example.com');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(actions.signInCalls, 1);
    expect(actions.resendCalls, 0);

    await tester.enterText(
      find.widgetWithText(TextField, 'Verification code'),
      '123456',
    );
    await tester.tap(find.text('Verify and continue'));
    await tester.pumpAndSettle();

    expect(actions.signInCalls, 1);
    expect(actions.resendCalls, 0);
    expect(actions.verifySignInCalls, 1);
  });

  testWidgets(
    'incorrect-code error keeps the code screen, shows mapped message, and makes no extra send',
    (tester) async {
      final actions = FakeClerkEmailCodeActions();
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.enterText(find.byType(TextField).first, 'user@example.com');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      actions.nextError = 'form_code_incorrect';
      await tester.enterText(
        find.widgetWithText(TextField, 'Verification code'),
        '000000',
      );
      await tester.tap(find.text('Verify and continue'));
      await tester.pumpAndSettle();

      expect(
        find.text(
          'That code is incorrect or expired. Use the newest email from Clerk, or tap Resend code.',
        ),
        findsOneWidget,
      );
      expect(find.text('Check your email'), findsOneWidget);
      expect(
        find.widgetWithText(TextField, 'Verification code'),
        findsOneWidget,
      );
      expect(actions.signInCalls, 1);
      expect(actions.resendCalls, 0);
      expect(actions.isSignedIn, isFalse);
    },
  );

  testWidgets('keyboard submit while working is ignored', (tester) async {
    final actions = FakeClerkEmailCodeActions()..simulateDelay = true;
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.enterText(find.byType(TextField).first, 'user@example.com');

    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(actions.signInCalls, 1);

    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(actions.signInCalls, 1);

    await tester.pumpAndSettle();
  });

  testWidgets(
    'the newest email notice appears after initial send and after resend',
    (tester) async {
      final actions = FakeClerkEmailCodeActions();
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.enterText(find.byType(TextField).first, 'user@example.com');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(
        find.text('Use the newest email; earlier codes no longer work.'),
        findsOneWidget,
      );

      await tester.tap(find.text('Resend code'));
      await tester.pumpAndSettle();
      expect(
        find.text('Use the newest email; earlier codes no longer work.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'required names block submit with \'Enter your first and last name.\'',
    (tester) async {
      final actions = FakeClerkEmailCodeActions();
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.tap(find.text('New to Karmi? Create an account'));
      await tester.pumpAndSettle();

      expect(find.text('First name (required)'), findsOneWidget);
      expect(find.text('Last name (required)'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'user@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        'ValidPassword12345',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        'ValidPassword12345',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 0);
      expect(find.text('Enter your first and last name.'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextField, 'First name (required)'),
        'Ada',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 0);
      expect(find.text('Enter your first and last name.'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextField, 'Last name (required)'),
        'Lovelace',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 1);
    },
  );

  testWidgets(
    'min length 15 blocks a 14-char password and allows a 15-char one',
    (tester) async {
      final actions = FakeClerkEmailCodeActions();
      await pumpHost(tester, ClerkSignInCard(actions: actions));
      await tester.tap(find.text('New to Karmi? Create an account'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'First name (required)'),
        'Ada',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Last name (required)'),
        'Lovelace',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'user@example.com',
      );

      // 14-char password
      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        '12345678901234',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        '12345678901234',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 0);
      expect(
        find.text('Password must be at least 15 characters.'),
        findsOneWidget,
      );

      // 15-char password
      await tester.enterText(
        find.widgetWithText(TextField, 'Create a password'),
        '123456789012345',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Confirm password'),
        '123456789012345',
      );
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(actions.signUpCalls, 1);
      expect(actions.lastPassword, '123456789012345');
    },
  );

  testWidgets('helper text \'At least 15 characters.\' shown', (tester) async {
    final actions = FakeClerkEmailCodeActions();
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.tap(find.text('New to Karmi? Create an account'));
    await tester.pumpAndSettle();

    expect(find.text('At least 15 characters.'), findsOneWidget);
  });

  testWidgets('Clerk sign-up errors map pwned and too-short passwords', (
    tester,
  ) async {
    final actions = FakeClerkEmailCodeActions();
    await pumpHost(tester, ClerkSignInCard(actions: actions));
    await tester.tap(find.text('New to Karmi? Create an account'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'First name (required)'),
      'Ada',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Last name (required)'),
      'Lovelace',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Email address'),
      'user@example.com',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Create a password'),
      '123456789012345',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Confirm password'),
      '123456789012345',
    );

    actions.nextError = 'form_password_pwned: password found in breach';
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(
      find.text(
        'This password appears in a known data breach. Choose a different one.',
      ),
      findsOneWidget,
    );

    actions.nextError = 'form_password_length_too_short';
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(
      find.text('Password must be at least 15 characters.'),
      findsOneWidget,
    );
  });
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
  @override
  int passwordMinLength = 15;
  @override
  bool firstNameRequired = true;
  @override
  bool lastNameRequired = true;
  bool requireFirstName = false;
  String? nextError;
  bool _signInAwaitingCode = false;
  bool _signUpAwaitingCode = false;
  final List<clerk.Field> _missing = [];
  int signInCalls = 0;
  int verifySignInCalls = 0;
  int signUpCalls = 0;
  int verifySignUpCalls = 0;
  int resendCalls = 0;
  String? lastPassword;
  String? lastPasswordConfirmation;
  String? lastVerifiedSignInCode;
  String? lastVerifiedSignUpCode;
  bool simulateDelay = false;
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
    if (simulateDelay) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    if (nextError != null) return _error(onError);
    if (code == null) {
      _signInAwaitingCode = true;
    } else {
      _signInAwaitingCode = false;
      isSignedIn = true;
    }
  }

  @override
  Future<void> verifySignInCode(
    String email,
    String code,
    ClerkFlowErrorHandler onError,
  ) async {
    verifySignInCalls++;
    lastVerifiedSignInCode = code;
    if (simulateDelay) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    if (nextError != null) return _error(onError);
    _signInAwaitingCode = false;
    isSignedIn = true;
  }

  @override
  Future<void> verifySignUpCode(
    String code,
    ClerkFlowErrorHandler onError,
  ) async {
    verifySignUpCalls++;
    lastVerifiedSignUpCode = code;
    if (simulateDelay) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    if (nextError != null) return _error(onError);
    _signUpAwaitingCode = false;
    isSignedIn = true;
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
