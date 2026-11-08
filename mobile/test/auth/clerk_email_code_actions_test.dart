import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/clerk_email_code_actions.dart';
import 'package:karmi_app/auth/account_rules.dart';
import 'package:url_launcher/url_launcher.dart';

import '../support/fake_clerk_actions.dart';

void main() {
  group('missingFieldsMessage', () {
    test('formats a single field name', () {
      expect(
        missingFieldsMessage(['username']),
        'Clerk still needs: username.',
      );
    });

    test('formats multiple field names in order', () {
      expect(
        missingFieldsMessage(['first_name', 'last_name', 'phone_number']),
        'Clerk still needs: first_name, last_name, phone_number.',
      );
    });

    test('formats empty field names list', () {
      expect(
        missingFieldsMessage([]),
        'Google sign-in did not finish. Please try again.',
      );
    });
  });

  group('ssoStartFailureOrNull', () {
    test(
      'returns GoogleSignInError when launch failed and no other progress',
      () {
        final failure = ssoStartFailureOrNull(
          launched: false,
          isSignedIn: false,
          isTransferring: false,
          ssoCallbackReceived: false,
        );
        expect(failure, isA<GoogleSignInError>());
        expect(
          failure?.message,
          'Google sign-in could not start. Please try again.',
        );
      },
    );

    test('returns null when browser launch succeeded', () {
      expect(
        ssoStartFailureOrNull(
          launched: true,
          isSignedIn: false,
          isTransferring: false,
          ssoCallbackReceived: false,
        ),
        isNull,
      );
    });

    test('returns null when user is already signed in', () {
      expect(
        ssoStartFailureOrNull(
          launched: false,
          isSignedIn: true,
          isTransferring: false,
          ssoCallbackReceived: false,
        ),
        isNull,
      );
    });

    test('returns null when transfer is in progress', () {
      expect(
        ssoStartFailureOrNull(
          launched: false,
          isSignedIn: false,
          isTransferring: true,
          ssoCallbackReceived: false,
        ),
        isNull,
      );
    });

    test('returns null when SSO callback was received', () {
      expect(
        ssoStartFailureOrNull(
          launched: false,
          isSignedIn: false,
          isTransferring: false,
          ssoCallbackReceived: true,
        ),
        isNull,
      );
    });
  });

  group('shouldIgnoreResume', () {
    test('ignores when completer is completed', () {
      expect(
        shouldIgnoreResume(isCompleted: true, ssoCallbackReceived: false),
        isTrue,
      );
    });

    test('ignores when SSO callback was received', () {
      expect(
        shouldIgnoreResume(isCompleted: false, ssoCallbackReceived: true),
        isTrue,
      );
    });

    test('does not ignore when uncompleted and callback not received', () {
      expect(
        shouldIgnoreResume(isCompleted: false, ssoCallbackReceived: false),
        isFalse,
      );
    });
  });

  group('shouldCancelOnResume', () {
    test(
      'cancels when uncompleted, callback not received, not signed in, and not transferring',
      () {
        expect(
          shouldCancelOnResume(
            isCompleted: false,
            ssoCallbackReceived: false,
            isSignedIn: false,
            isTransferring: false,
          ),
          isTrue,
        );
      },
    );

    test('does not cancel when completed', () {
      expect(
        shouldCancelOnResume(
          isCompleted: true,
          ssoCallbackReceived: false,
          isSignedIn: false,
          isTransferring: false,
        ),
        isFalse,
      );
    });

    test('does not cancel when SSO callback was received', () {
      expect(
        shouldCancelOnResume(
          isCompleted: false,
          ssoCallbackReceived: true,
          isSignedIn: false,
          isTransferring: false,
        ),
        isFalse,
      );
    });

    test('does not cancel when signed in', () {
      expect(
        shouldCancelOnResume(
          isCompleted: false,
          ssoCallbackReceived: false,
          isSignedIn: true,
          isTransferring: false,
        ),
        isFalse,
      );
    });

    test('does not cancel when transfer is in progress', () {
      expect(
        shouldCancelOnResume(
          isCompleted: false,
          ssoCallbackReceived: false,
          isSignedIn: false,
          isTransferring: true,
        ),
        isFalse,
      );
    });
  });

  group('launchSsoBrowser', () {
    test('returns false when urlLauncher returns false', () async {
      final launched = await launchSsoBrowser(
        redirectUrl: 'https://accounts.google.com/o/oauth2/auth',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => false,
      );
      expect(launched, isFalse);
    });

    test('returns false when urlLauncher throws', () async {
      final launched = await launchSsoBrowser(
        redirectUrl: 'https://accounts.google.com/o/oauth2/auth',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async =>
            throw Exception('Launch failed'),
      );
      expect(launched, isFalse);
    });

    test('returns false when redirectUrl is null', () async {
      final launched = await launchSsoBrowser(
        redirectUrl: null,
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => true,
      );
      expect(launched, isFalse);
    });

    test('returns false when redirectUrl is empty', () async {
      final launched = await launchSsoBrowser(
        redirectUrl: '',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => true,
      );
      expect(launched, isFalse);
    });

    test(
      'returns true when urlLauncher returns true and passes mode',
      () async {
        Uri? passedUri;
        LaunchMode? passedMode;
        final launched = await launchSsoBrowser(
          redirectUrl: 'https://accounts.google.com/o/oauth2/auth',
          urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async {
            passedUri = uri;
            passedMode = mode;
            return true;
          },
          mode: LaunchMode.externalApplication,
        );
        expect(launched, isTrue);
        expect(
          passedUri,
          Uri.parse('https://accounts.google.com/o/oauth2/auth'),
        );
        expect(passedMode, LaunchMode.externalApplication);
      },
    );
  });

  group('postSsoSignInLaunchAndDecision', () {
    test('returns GoogleSignInError when launch returns false (a)', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: 'https://accounts.google.com/o/oauth2/auth',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => false,
      );
      expect(failure, isA<GoogleSignInError>());
      expect(
        (failure as GoogleSignInError?)?.message,
        'Google sign-in could not start. Please try again.',
      );
    });

    test('returns GoogleSignInError when launch throws (b)', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: 'https://accounts.google.com/o/oauth2/auth',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async =>
            throw Exception('Browser launch failed'),
      );
      expect(failure, isA<GoogleSignInError>());
      expect(
        (failure as GoogleSignInError?)?.message,
        'Google sign-in could not start. Please try again.',
      );
    });

    test('returns GoogleSignInError when redirect is null (c)', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: null,
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => true,
      );
      expect(failure, isA<GoogleSignInError>());
      expect(
        (failure as GoogleSignInError?)?.message,
        'Google sign-in could not start. Please try again.',
      );
    });

    test('returns GoogleSignInError when redirect is empty (c)', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: '',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => true,
      );
      expect(failure, isA<GoogleSignInError>());
      expect(
        (failure as GoogleSignInError?)?.message,
        'Google sign-in could not start. Please try again.',
      );
    });

    test('returns null when browser launch succeeds', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: 'https://accounts.google.com/o/oauth2/auth',
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => true,
      );
      expect(failure, isNull);
    });

    test(
      'returns GoogleSignInSuccess when user is already signed in',
      () async {
        final result = await postSsoSignInLaunchAndDecision(
          redirectUrl: null,
          urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async =>
              false,
          isSignedIn: true,
        );
        expect(result, isA<GoogleSignInSuccess>());
      },
    );

    test('returns null when transfer is active', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: null,
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => false,
        isTransferring: true,
      );
      expect(failure, isNull);
    });

    test('returns null when SSO callback was received', () async {
      final failure = await postSsoSignInLaunchAndDecision(
        redirectUrl: null,
        urlLauncher: (uri, {mode = LaunchMode.platformDefault}) async => false,
        ssoCallbackReceived: true,
      );
      expect(failure, isNull);
    });
  });

  group('SsoCallbackHandler', () {
    final callback = Uri.parse(
      'ai.karmi.app://sso-callback?rotating_token_nonce=abc',
    );

    late List<Uri> parsed;
    late List<GoogleSignInError> failures;
    late int started;
    late int processed;

    SsoCallbackHandler build(Future<Object?> Function(Uri) parse) {
      parsed = [];
      failures = [];
      started = 0;
      processed = 0;
      return SsoCallbackHandler(
        parse: (uri) {
          parsed.add(uri);
          return parse(uri);
        },
        onStarted: () => started++,
        onFailure: failures.add,
        onProcessed: () async {
          processed++;
        },
      );
    }

    test('successful exchange hands over to the state check', () async {
      final handler = build((_) async => true);
      await handler.handle(callback);
      expect(parsed, [callback]);
      expect(started, 1);
      expect(processed, 1);
      expect(failures, isEmpty);
    });

    test('failed exchange surfaces the mapped error without waiting', () async {
      final error = clerkErrorWithCodes(['form_code_incorrect']);
      final handler = build((_) => Future.error(error));
      await handler.handle(callback);
      expect(failures, hasLength(1));
      expect(failures.single.message, issueFromClerkError(error).message);
      expect(processed, 0);
    });

    test(
      'unrelated links are ignored and do not consume the attempt',
      () async {
        final handler = build((_) async => true);
        await handler.handle(Uri.parse('https://example.com/?x=1'));
        await handler.handle(Uri.parse('ai.karmi.app://other'));
        expect(parsed, isEmpty);
        expect(started, 0);
        await handler.handle(callback);
        expect(parsed, [callback]);
      },
    );

    test('duplicate callbacks are processed only once', () async {
      final handler = build((_) async => true);
      await Future.wait([handler.handle(callback), handler.handle(callback)]);
      await handler.handle(callback);
      expect(parsed, hasLength(1));
      expect(started, 1);
      expect(processed, 1);
    });
  });
}
