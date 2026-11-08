import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_auth/src/models/api/external_error.dart';
import 'package:karmi_app/auth/clerk_email_code_actions.dart';

/// In-memory Clerk stand-in. Set [nextError] to make the next call fail with
/// that error; set [requireSecondFactor] to make password sign-in ask for a code.
class FakeClerkEmailCodeActions implements ClerkEmailCodeActions {
  @override
  bool isSignedIn = false;
  @override
  bool isNotAvailable = false;
  @override
  int passwordMinLength = 8;
  @override
  List<clerk.Field> get signUpMissingFields => const [];

  bool _signUpAwaitingCode = false;
  bool _signInAwaitingCode = false;
  bool _signInNeedsSecondFactor = false;

  /// Simulates an unknown non-complete Clerk state after password sign-in.
  bool stallAfterPassword = false;
  Object? nextError;
  bool requireSecondFactor = false;
  GoogleSignInResult googleSignInResult = const GoogleSignInSuccess();
  GoogleSignInResult get nextGoogleResult => googleSignInResult;
  set nextGoogleResult(GoogleSignInResult value) => googleSignInResult = value;

  final List<String> calls = [];
  String? lastSignUpUsername;
  String? lastSignUpFirstName;
  String? lastSignUpLastName;
  String? lastSignInIdentifier;
  String? lastPassword;
  String? lastCode;
  String? lastResetEmail;
  String? lastResetCode;
  String? lastResetPassword;

  /// After a successful reset Clerk asks for a second factor instead of
  /// signing in (mirrors [requireSecondFactor] for password sign-in).
  bool resetRequiresSecondFactor = false;
  bool _passwordResetAwaitingCode = false;

  @override
  bool get passwordResetAwaitingCode => _passwordResetAwaitingCode;

  @override
  Future<void> startPasswordReset({
    required String email,
    required ClerkFlowErrorHandler onError,
  }) async {
    calls.add('startPasswordReset');
    lastResetEmail = email;
    if (nextError != null) return _maybeFail(onError);
    _passwordResetAwaitingCode = true;
  }

  @override
  Future<void> completePasswordReset({
    required String code,
    required String newPassword,
    required ClerkFlowErrorHandler onError,
  }) async {
    calls.add('completePasswordReset');
    lastResetCode = code;
    lastResetPassword = newPassword;
    if (nextError != null) return _maybeFail(onError);
    _passwordResetAwaitingCode = false;
    if (resetRequiresSecondFactor) {
      _signInNeedsSecondFactor = true;
    } else {
      isSignedIn = true;
    }
  }

  @override
  bool get signUpAwaitingCode => _signUpAwaitingCode;
  @override
  bool get signInAwaitingCode => _signInAwaitingCode;
  @override
  bool get signInNeedsSecondFactor => _signInNeedsSecondFactor;
  @override
  String? get signInStatus => stallAfterPassword
      ? 'needs_identifier'
      : _signInNeedsSecondFactor
      ? 'needs_second_factor'
      : null;

  @override
  Future<void> sendSignInCode(ClerkFlowErrorHandler onError) async {
    calls.add('sendSignInCode');
    if (nextError != null) return _maybeFail(onError);
    // Like Clerk: the code is only sent once the second factor is prepared.
    _signInNeedsSecondFactor = false;
    _signInAwaitingCode = true;
  }

  void _maybeFail(ClerkFlowErrorHandler onError) {
    final error = nextError;
    if (error != null) {
      nextError = null;
      onError(error);
    }
  }

  @override
  Future<void> signUp({
    required String email,
    required String firstName,
    String? lastName,
    required String username,
    required String password,
    required ClerkFlowErrorHandler onError,
  }) async {
    calls.add('signUp');
    lastSignUpFirstName = firstName;
    lastSignUpLastName = lastName;
    lastSignUpUsername = username;
    lastPassword = password;
    if (nextError != null) return _maybeFail(onError);
    _signUpAwaitingCode = true;
  }

  @override
  Future<void> signIn({
    required String identifier,
    required String password,
    required ClerkFlowErrorHandler onError,
  }) async {
    calls.add('signIn');
    lastSignInIdentifier = identifier;
    lastPassword = password;
    if (nextError != null) return _maybeFail(onError);
    if (stallAfterPassword) return;
    if (requireSecondFactor) {
      // Real Clerk: password accepted, second factor required, no code sent yet.
      _signInNeedsSecondFactor = true;
    } else {
      isSignedIn = true;
    }
  }

  @override
  Future<void> verifySignUpCode(
    String code,
    ClerkFlowErrorHandler onError,
  ) async {
    calls.add('verifySignUp');
    lastCode = code;
    if (nextError != null) return _maybeFail(onError);
    _signUpAwaitingCode = false;
    isSignedIn = true;
  }

  @override
  Future<void> verifySignInCode(
    String identifier,
    String code,
    ClerkFlowErrorHandler onError,
  ) async {
    calls.add('verifySignIn');
    lastCode = code;
    if (nextError != null) return _maybeFail(onError);
    _signInAwaitingCode = false;
    isSignedIn = true;
  }

  @override
  Future<void> resendCode(ClerkFlowErrorHandler onError) async {
    calls.add('resend');
  }

  @override
  Future<void> reset(ClerkFlowErrorHandler onError) async {
    _signUpAwaitingCode = false;
    _signInAwaitingCode = false;
    _signInNeedsSecondFactor = false;
  }

  @override
  Future<GoogleSignInResult> signInWithGoogle() async {
    calls.add('signInWithGoogle');
    if (googleSignInResult is GoogleSignInSuccess) {
      isSignedIn = true;
    }
    return googleSignInResult;
  }
}

/// A Clerk error carrying one server [ExternalError] per code, shaped like the
/// SDK's response for a failed form submission.
clerk.ClerkError clerkErrorWithCodes(List<String> codes) => clerk.ClerkError(
  code: clerk.ClerkErrorCode.serverErrorResponse,
  message: '{arg} (ERROR RECEIVED FROM SERVER)',
  errors: ExternalErrorCollection(
    errors: [
      for (final code in codes)
        ExternalError(message: 'server said $code', code: code),
    ],
  ),
);
