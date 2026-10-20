import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:flutter/material.dart';

typedef ClerkFlowErrorHandler = void Function(Object error);

/// Small seam between Karmi's auth form and Clerk, allowing the form to be
/// tested without a live Clerk tenant.
abstract interface class ClerkEmailCodeActions {
  bool get isSignedIn;
  bool get isNotAvailable;
  bool get supportsEmailCode;
  bool get legalConsentRequired;
  int get passwordMinLength;
  bool get firstNameRequired;
  bool get lastNameRequired;
  List<clerk.Field> get signUpMissingFields;
  bool get signInAwaitingCode;
  bool get signUpAwaitingCode;
  bool get isMidSignUp;
  String? get signUpEmail;

  Future<void> signIn(
    String email,
    String? code,
    ClerkFlowErrorHandler onError,
  );
  Future<void> verifySignInCode(
    String email,
    String code,
    ClerkFlowErrorHandler onError,
  );
  Future<void> signUp(
    String email,
    String? firstName,
    String? lastName,
    String? code,
    ClerkFlowErrorHandler onError, {
    String? password,
    String? passwordConfirmation,
  });
  Future<void> verifySignUpCode(
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
  bool get supportsEmailCode => auth.env.supportsEmailCode;

  @override
  bool get legalConsentRequired => auth.env.user.signUp.legalConsentEnabled;

  @override
  int get passwordMinLength {
    final min = auth.env.user.passwordSettings.minLength;
    return min > 0 ? min : 15;
  }

  @override
  bool get firstNameRequired =>
      auth.env.user.attributes[clerk.UserAttribute.firstName]?.isRequired ==
      true;

  @override
  bool get lastNameRequired =>
      auth.env.user.attributes[clerk.UserAttribute.lastName]?.isRequired ==
      true;

  @override
  List<clerk.Field> get signUpMissingFields =>
      auth.signUp?.missingFields ?? const [];

  @override
  bool get signInAwaitingCode =>
      auth.signIn?.isVerifying(clerk.Stage.first, clerk.Strategy.emailCode) ==
      true;

  @override
  bool get signUpAwaitingCode =>
      auth.signUp?.unverified(clerk.Field.emailAddress) == true;

  @override
  bool get isMidSignUp =>
      !auth.isSignedIn &&
      auth.signUp != null &&
      auth.signUp!.unverified(clerk.Field.emailAddress) == false &&
      auth.signUp!.missingFields.contains(clerk.Field.password);

  @override
  String? get signUpEmail => auth.signUp?.emailAddress;
  Future<void> _safely<T>(
    Future<T> Function() operation,
    ClerkFlowErrorHandler onError,
  ) async {
    await auth.safelyCall(
      context,
      operation,
      onError: (error) => onError(error),
    );
  }

  @override
  Future<void> signIn(
    String email,
    String? code,
    ClerkFlowErrorHandler onError,
  ) => _safely(
    () => auth.attemptSignIn(
      strategy: clerk.Strategy.emailCode,
      identifier: email,
      code: code,
    ),
    onError,
  );
  @override
  Future<void> verifySignInCode(
    String email,
    String code,
    ClerkFlowErrorHandler onError,
  ) => _safely(
    () => auth.attemptSignIn(
      strategy: clerk.Strategy.emailCode,
      identifier: email,
      code: code,
    ),
    onError,
  );

  @override
  Future<void> verifySignUpCode(
    String code,
    ClerkFlowErrorHandler onError,
  ) => _safely(
    () => auth.attemptSignUp(
      strategy: clerk.Strategy.emailCode,
      code: code,
    ),
    onError,
  );


  @override
  Future<void> signUp(
    String email,
    String? firstName,
    String? lastName,
    String? code,
    ClerkFlowErrorHandler onError, {
    String? password,
    String? passwordConfirmation,
  }) => _safely(
    () => auth.attemptSignUp(
      strategy: clerk.Strategy.emailCode,
      emailAddress: email.isNotEmpty ? email : null,
      firstName: firstName,
      lastName: lastName,
      password: password,
      passwordConfirmation: passwordConfirmation,
      code: code,
    ),
    onError,
  );

  @override
  Future<void> resendCode(ClerkFlowErrorHandler onError) =>
      _safely(() => auth.resendCode(clerk.Strategy.emailCode), onError);

  @override
  Future<void> reset(ClerkFlowErrorHandler onError) =>
      _safely(() => auth.resetClient(), onError);
}
