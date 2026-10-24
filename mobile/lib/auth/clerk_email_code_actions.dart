import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:flutter/material.dart';

typedef ClerkFlowErrorHandler = void Function(Object error);

/// Seam between Karmi's account form and Clerk. Identity, verification and
/// session state stay with Clerk; the form only asks for what Clerk needs.
abstract interface class ClerkEmailCodeActions {
  bool get isSignedIn;
  bool get isNotAvailable;
  int get passwordMinLength;

  /// Clerk fields still required before the sign-up can proceed.
  List<clerk.Field> get signUpMissingFields;

  /// True while Clerk waits for the email code of a sign-up.
  bool get signUpAwaitingCode;

  /// True while Clerk waits for an email code second factor after sign-in.
  bool get signInAwaitingCode;

  /// Create the account (password strategy). Clerk then emails a code.
  Future<void> signUp({
    required String email,
    required String firstName,
    String? lastName,
    required String username,
    required String password,
    required ClerkFlowErrorHandler onError,
  });

  /// Sign in with password. Clerk may then require an email code.
  Future<void> signIn({
    required String identifier,
    required String password,
    required ClerkFlowErrorHandler onError,
  });

  Future<void> verifySignUpCode(String code, ClerkFlowErrorHandler onError);
  Future<void> verifySignInCode(
    String identifier,
    String code,
    ClerkFlowErrorHandler onError,
  );
  Future<void> resendCode(ClerkFlowErrorHandler onError);
  Future<void> reset(ClerkFlowErrorHandler onError);
}

class ClerkSdkEmailCodeActions implements ClerkEmailCodeActions {
  ClerkSdkEmailCodeActions(this.auth, this.context);

  final ClerkAuthState auth;
  final BuildContext context;

  @override
  bool get isSignedIn => auth.isSignedIn;

  @override
  bool get isNotAvailable => auth.isNotAvailable;

  @override
  int get passwordMinLength {
    final min = auth.env.user.passwordSettings.minLength;
    return min > 0 ? min : 8;
  }

  @override
  List<clerk.Field> get signUpMissingFields =>
      auth.signUp?.missingFields ?? const [];

  @override
  bool get signUpAwaitingCode =>
      auth.signUp?.unverified(clerk.Field.emailAddress) == true;

  @override
  bool get signInAwaitingCode =>
      auth.signIn?.isVerifying(clerk.Stage.second, clerk.Strategy.emailCode) ==
      true;

  Future<void> _safely(
    Future<void> Function() operation,
    ClerkFlowErrorHandler onError,
  ) async {
    await auth.safelyCall(context, operation, onError: (error) => onError(error));
  }

  @override
  Future<void> signUp({
    required String email,
    required String firstName,
    String? lastName,
    required String username,
    required String password,
    required ClerkFlowErrorHandler onError,
  }) => _safely(
    () => auth.attemptSignUp(
      strategy: clerk.Strategy.emailCode,
      emailAddress: email,
      firstName: firstName,
      lastName: lastName,
      username: username,
      password: password,
      passwordConfirmation: password,
    ),
    onError,
  );

  @override
  Future<void> signIn({
    required String identifier,
    required String password,
    required ClerkFlowErrorHandler onError,
  }) => _safely(
    () => auth.attemptSignIn(
      strategy: clerk.Strategy.password,
      identifier: identifier,
      password: password,
    ),
    onError,
  );

  @override
  Future<void> verifySignUpCode(String code, ClerkFlowErrorHandler onError) =>
      _safely(
        () => auth.attemptSignUp(strategy: clerk.Strategy.emailCode, code: code),
        onError,
      );

  @override
  Future<void> verifySignInCode(
    String identifier,
    String code,
    ClerkFlowErrorHandler onError,
  ) => _safely(
    () => auth.attemptSignIn(
      strategy: clerk.Strategy.emailCode,
      identifier: identifier,
      code: code,
    ),
    onError,
  );

  @override
  Future<void> resendCode(ClerkFlowErrorHandler onError) => _safely(
    () => auth.resendCode(clerk.Strategy.emailCode),
    onError,
  );

  @override
  Future<void> reset(ClerkFlowErrorHandler onError) =>
      _safely(() => auth.resetClient(), onError);
}
