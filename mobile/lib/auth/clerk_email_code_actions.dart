import 'dart:async';

import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'account_rules.dart';
import 'clerk_sso.dart';

typedef ClerkFlowErrorHandler = void Function(Object error);
typedef UrlLauncherFunction = Future<bool> Function(Uri url, {LaunchMode mode});

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

/// Formats a user-facing message describing missing Clerk sign-up fields after SSO transfer.
String missingFieldsMessage(Iterable<String> fieldNames) {
  final fields = fieldNames.where((f) => f.isNotEmpty).join(', ');
  if (fields.isEmpty) {
    return 'Google sign-in did not finish. Please try again.';
  }
  return 'Clerk still needs: $fields.';
}

/// Pure decision helper returning a [GoogleSignInError] if the SSO browser launch
/// could not start and no completion, transfer, or callback link is active.
GoogleSignInError? ssoStartFailureOrNull({
  required bool launched,
  bool isSignedIn = false,
  bool isTransferring = false,
  bool ssoCallbackReceived = false,
}) {
  if (isSignedIn || isTransferring || ssoCallbackReceived) {
    return null;
  }
  if (!launched) {
    return const GoogleSignInError(
      'Google sign-in could not start. Please try again.',
    );
  }
  return null;
}

/// Pure helper that attempts to launch the external SSO browser given [redirectUrl]
/// and [urlLauncher]. Returns `true` if launched successfully, `false` if redirect
/// is missing, launch returned false, or launch threw.
Future<bool> launchSsoBrowser({
  required String? redirectUrl,
  required UrlLauncherFunction urlLauncher,
  LaunchMode mode = LaunchMode.platformDefault,
}) async {
  if (redirectUrl == null || redirectUrl.isEmpty) {
    return false;
  }
  try {
    final uri = Uri.parse(redirectUrl);
    return await urlLauncher(uri, mode: mode);
  } catch (_) {
    return false;
  }
}

/// Pure decision helper resolving the post-ssoSignIn launch outcome into a
/// [GoogleSignInResult] (returning [GoogleSignInSuccess] if signed in) or null
/// if launch succeeded or the sign-in session progressed (transferring or
/// callback received).
Future<GoogleSignInResult?> postSsoSignInLaunchAndDecision({
  required String? redirectUrl,
  required UrlLauncherFunction urlLauncher,
  LaunchMode mode = LaunchMode.platformDefault,
  bool isSignedIn = false,
  bool isTransferring = false,
  bool ssoCallbackReceived = false,
}) async {
  final launched = await launchSsoBrowser(
    redirectUrl: redirectUrl,
    urlLauncher: urlLauncher,
    mode: mode,
  );
  if (isSignedIn) {
    return const GoogleSignInSuccess();
  }
  return ssoStartFailureOrNull(
    launched: launched,
    isSignedIn: isSignedIn,
    isTransferring: isTransferring,
    ssoCallbackReceived: ssoCallbackReceived,
  );
}

/// Pure decision helper deciding whether to ignore an app resume event.
bool shouldIgnoreResume({
  required bool isCompleted,
  required bool ssoCallbackReceived,
}) {
  return isCompleted || ssoCallbackReceived;
}

/// Pure decision helper deciding whether to cancel the Google SSO sign-in on app resume.
bool shouldCancelOnResume({
  required bool isCompleted,
  required bool ssoCallbackReceived,
  required bool isSignedIn,
  required bool isTransferring,
}) {
  return !isCompleted && !ssoCallbackReceived && !isSignedIn && !isTransferring;
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

  /// True while Clerk waits for the emailed code of a password reset
  /// (the code has been sent).
  bool get passwordResetAwaitingCode;

  /// Start a password reset: Clerk creates a sign-in for [email] and emails a
  /// six-digit code. Calling it again sends a fresh code.
  Future<void> startPasswordReset({
    required String email,
    required ClerkFlowErrorHandler onError,
  });

  /// Finish the reset with the emailed [code] and [newPassword]. On success
  /// Clerk signs the user in, or asks for a second factor like a normal
  /// password sign-in.
  Future<void> completePasswordReset({
    required String code,
    required String newPassword,
    required ClerkFlowErrorHandler onError,
  });

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
    UrlLauncherFunction? urlLauncher,
  }) : _callbackLinks = callbackLinks,
       _urlLauncher =
           urlLauncher ??
           ((url, {mode = LaunchMode.platformDefault}) =>
               launchUrl(url, mode: mode));

  final ClerkAuthState auth;
  final BuildContext context;
  final Stream<Uri>? _callbackLinks;
  final UrlLauncherFunction _urlLauncher;

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

  @override
  bool get passwordResetAwaitingCode =>
      auth.signIn?.isVerifying(
        clerk.Stage.first,
        clerk.Strategy.resetPasswordEmailCode,
      ) ==
      true;

  // initiatePasswordReset creates a fresh sign-in with the reset strategy,
  // which makes Clerk email the code (auth.dart initiatePasswordReset).
  @override
  Future<void> startPasswordReset({
    required String email,
    required ClerkFlowErrorHandler onError,
  }) => _safely(
    () => auth.initiatePasswordReset(
      identifier: email,
      strategy: clerk.Strategy.resetPasswordEmailCode,
    ),
    onError,
  );

  // No identifier: the sign-in created by startPasswordReset is reused, so
  // the SDK attempts the reset factor instead of creating a new sign-in.
  @override
  Future<void> completePasswordReset({
    required String code,
    required String newPassword,
    required ClerkFlowErrorHandler onError,
  }) => _safely(
    () => auth.attemptSignIn(
      strategy: clerk.Strategy.resetPasswordEmailCode,
      code: code,
      password: newPassword,
    ),
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
            final message = missingFieldsMessage(missing.map((f) => f.name));
            finish(GoogleSignInError(message));
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
        if (shouldIgnoreResume(
          isCompleted: completer.isCompleted,
          ssoCallbackReceived: ssoCallbackReceived,
        )) {
          return;
        }
        cancelTimer?.cancel();
        cancelTimer = Timer(const Duration(milliseconds: 750), () async {
          if (shouldIgnoreResume(
            isCompleted: completer.isCompleted,
            ssoCallbackReceived: ssoCallbackReceived,
          )) {
            return;
          }
          await checkState();
          if (shouldCancelOnResume(
            isCompleted: completer.isCompleted,
            ssoCallbackReceived: ssoCallbackReceived,
            isSignedIn: auth.isSignedIn,
            isTransferring: isTransferring,
          )) {
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
      final redirect =
          auth.config.redirectionGenerator?.call(
            context,
            clerk.Strategy.oauthGoogle,
          ) ??
          kClerkOAuthRedirectUri;
      await auth.safelyCall(
        context,
        () => auth.oauthSignIn(
          strategy: clerk.Strategy.oauthGoogle,
          redirect: redirect,
        ),
        onError: (error) {
          final issue = issueFromClerkError(error);
          finish(GoogleSignInError(issue.message));
        },
      );
    } catch (e) {
      finish(GoogleSignInError(issueFromClerkError(e).message));
    }

    if (!completer.isCompleted) {
      final redirectUrl =
          auth.signIn?.firstFactorVerification?.externalVerificationRedirectUrl;
      final decision = await postSsoSignInLaunchAndDecision(
        redirectUrl: redirectUrl,
        urlLauncher: _urlLauncher,
        mode: auth.config.defaultLaunchMode,
        isSignedIn: auth.isSignedIn,
        isTransferring: isTransferring,
        ssoCallbackReceived: ssoCallbackReceived,
      );
      if (decision != null) {
        finish(decision);
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
