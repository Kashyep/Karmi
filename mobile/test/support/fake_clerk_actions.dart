import 'package:clerk_auth/clerk_auth.dart' as clerk;
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
  Object? nextError;
  bool requireSecondFactor = false;

  final List<String> calls = [];
  String? lastSignUpUsername;
  String? lastSignUpFirstName;
  String? lastSignUpLastName;
  String? lastSignInIdentifier;
  String? lastPassword;
  String? lastCode;

  @override
  bool get signUpAwaitingCode => _signUpAwaitingCode;
  @override
  bool get signInAwaitingCode => _signInAwaitingCode;

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
    if (requireSecondFactor) {
      _signInAwaitingCode = true;
    } else {
      isSignedIn = true;
    }
  }

  @override
  Future<void> verifySignUpCode(String code, ClerkFlowErrorHandler onError) async {
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
  }
}
