import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/clerk_email_code_actions.dart';

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
    test('returns GoogleSignInError when launch failed and no other progress', () {
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
    });

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
    test('cancels when uncompleted, callback not received, not signed in, and not transferring', () {
      expect(
        shouldCancelOnResume(
          isCompleted: false,
          ssoCallbackReceived: false,
          isSignedIn: false,
          isTransferring: false,
        ),
        isTrue,
      );
    });

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
}
