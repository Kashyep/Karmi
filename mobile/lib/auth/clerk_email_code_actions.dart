import 'dart:async';

import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:flutter/material.dart';

import 'account_rules.dart';
import 'clerk_sso.dart';

typedef ClerkFlowErrorHandler = void Function(Object error);

/// Result of a Google SSO attempt.
sealed class GoogleSignInResult {
  const GoogleSignInResult();

  const factory GoogleSignInResult.success() = GoogleSignInSuccess;
  const factory GoogleSignInResult.cancelled() = GoogleSignInCancelled;
  const factory GoogleSignInResult.error(String message) = GoogleSignInError;
}

class GoogleSignInSuccess extends GoogleSignInResult {
  const GoogleSignInSuccess();
}

class GoogleSignInCancelled extends GoogleSignInResult {
  const GoogleSignInCancelled();
}

class GoogleSignInError extends GoogleSignInResult {
  const GoogleSignInError(this.message);
  final String message;
}

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

  /// True while Clerk waits for an email code second factor after sign-in
  /// (the code has been sent).
  bool get signInAwaitingCode;

  /// True when Clerk accepted the password but still requires a second factor
  /// (e.g. new-device verification) and no code has been sent yet.
  bool get signInNeedsSecondFactor;

  /// Raw Clerk sign-in status, for surfacing unexpected states to the user.
  String? get signInStatus;

  /// Ask Clerk to email the second-factor code for the current sign-in.
  Future<void> sendSignInCode(ClerkFlowErrorHandler onError);

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

  /// Initiates Google OAuth sign-in via external browser, handling any
  /// subsequent sign-in to sign-up transfer so new users are never dead-ended.
  Future<GoogleSignInResult> signInWithGoogle();
}

class ClerkSdkEmailCodeActions implements ClerkEmailCodeActions {
  ClerkSdkEmailCodeActions(
    this.auth,
    this.context, {
    Stream<Uri>? callbackLinks,
  }) : _callbackLinks = callbackLinks;

  final ClerkAuthState auth;
  final BuildContext context;
  final Stream<Uri>? _callbackLinks;

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

  @override
  bool get signInNeedsSecondFactor {
    final signIn = auth.signIn;
    if (signIn == null) return false;
    return (signIn.needsSecondFactor || signIn.needsClientTrust) &&
        !signInAwaitingCode;
  }

  @override
  String? get signInStatus => auth.signIn?.status.toString();

  // With no code, the SDK prepares (sends) the email code for the current
  // factor stage instead of attempting verification.
  @override
  Future<void> sendSignInCode(ClerkFlowErrorHandler onError) => _safely(
    () => auth.attemptSignIn(strategy: clerk.Strategy.emailCode),
    onError,
  );

  Future<void> _safely(
    Future<void> Function() operation,
    ClerkFlowErrorHandler onError,
  ) async {
    await auth.safelyCall(
      context,
      operation,
      onError: (error) => onError(error),
    );
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
        () =>
            auth.attemptSignUp(strategy: clerk.Strategy.emailCode, code: code),
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
  Future<void> resendCode(ClerkFlowErrorHandler onError) =>
      _safely(() => auth.resendCode(clerk.Strategy.emailCode), onError);

  @override
  Future<void> reset(ClerkFlowErrorHandler onError) =>
      _safely(() => auth.resetClient(), onError);

  @override
  Future<GoogleSignInResult> signInWithGoogle() async {
    if (isNotAvailable) {
      return const GoogleSignInError('Clerk authentication is not configured.');
    }

    final completer = Completer<GoogleSignInResult>();
    void finish(GoogleSignInResult result) {
      if (!completer.isCompleted) {
        completer.complete(result);
      }
    }

    bool ssoCallbackReceived = false;
    bool isTransferring = false;
    Timer? cancelTimer;
    Timer? callbackTimeoutTimer;

    Future<void> checkState() async {
      if (completer.isCompleted) return;
      if (auth.isSignedIn) {
        finish(const GoogleSignInSuccess());
        return;
      }
      if (auth.signIn?.isTransferable == true ||
          auth.signUp?.isTransferable == true) {
        if (isTransferring) return;
        isTransferring = true;
        try {
          await auth.transfer();
          if (auth.isSignedIn) {
            finish(const GoogleSignInSuccess());
            return;
          }
          final missing = auth.signUp?.missingFields ?? const [];
          if (missing.isNotEmpty) {
            final fields = missing.map((f) => f.name).join(', ');
            finish(GoogleSignInError('Clerk still needs: $fields.'));
            return;
          }
        } catch (e) {
          finish(GoogleSignInError(issueFromClerkError(e).message));
          return;
        } finally {
          isTransferring = false;
        }
      }
    }

    void listener() {
      unawaited(checkState());
    }

    auth.addListener(listener);

    final callbackStream = _callbackLinks ?? ssoCallbackStream;
    StreamSubscription<Uri>? callbackSub;
    callbackSub = callbackStream.listen((uri) {
      ssoCallbackReceived = true;
      cancelTimer?.cancel();
      cancelTimer = null;
      callbackTimeoutTimer ??= Timer(const Duration(seconds: 45), () {
        if (!completer.isCompleted) {
          finish(
            const GoogleSignInError(
              'Google sign-in did not finish. Please try again.',
            ),
          );
        }
      });
      unawaited(checkState());
    });

    AppLifecycleListener? lifecycleListener;
    lifecycleListener = AppLifecycleListener(
      onResume: () {
        if (completer.isCompleted || ssoCallbackReceived) {
          return;
        }
        cancelTimer?.cancel();
        cancelTimer = Timer(const Duration(milliseconds: 750), () async {
          if (completer.isCompleted || ssoCallbackReceived) {
            return;
          }
          await checkState();
          if (!completer.isCompleted &&
              !ssoCallbackReceived &&
              !auth.isSignedIn &&
              !isTransferring) {
            finish(const GoogleSignInCancelled());
          }
        });
      },
    );

    StreamSubscription<clerk.ClerkError>? errorSub;
    errorSub = auth.errorStream.listen((error) {
      final issue = issueFromClerkError(error);
      finish(GoogleSignInError(issue.message));
    });

    try {
      await auth.ssoSignIn(
        context,
        clerk.Strategy.oauthGoogle,
        onError: (error) {
          final issue = issueFromClerkError(error);
          finish(GoogleSignInError(issue.message));
        },
      );
    } catch (e) {
      finish(GoogleSignInError(issueFromClerkError(e).message));
    }

    if (!completer.isCompleted) {
      if (auth.isSignedIn) {
        finish(const GoogleSignInSuccess());
      } else {
        final redirectUrl = auth
            .signIn
            ?.firstFactorVerification
            ?.externalVerificationRedirectUrl;
        final redirectStarted = redirectUrl is String && redirectUrl.isNotEmpty;
        if (!redirectStarted && !isTransferring && !ssoCallbackReceived) {
          finish(
            const GoogleSignInError(
              'Google sign-in could not start. Please try again.',
            ),
          );
        }
      }
    }

    try {
      final result = await completer.future;
      return result;
    } finally {
      auth.removeListener(listener);
      lifecycleListener.dispose();
      cancelTimer?.cancel();
      callbackTimeoutTimer?.cancel();
      await callbackSub.cancel();
      await errorSub.cancel();
    }
  }
}
