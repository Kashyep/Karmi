import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/account_rules.dart';

import '../support/fake_clerk_actions.dart';

/// Builds a Clerk error with the given server codes.
clerk.ClerkError _clerkError(String first, [String? second]) =>
    clerkErrorWithCodes([first, if (second != null) second]);

void main() {
  group('isValidUsername', () {
    test('accepts 4 to 64 letters, digits, underscore and hyphen', () {
      expect(isValidUsername('abcd'), isTrue);
      expect(isValidUsername('Karmi_user-09'), isTrue);
      expect(isValidUsername('a' * 64), isTrue);
    });

    test('rejects values shorter than 4 characters', () {
      expect(isValidUsername(''), isFalse);
      expect(isValidUsername('abc'), isFalse);
    });

    test('rejects values longer than 64 characters', () {
      expect(isValidUsername('a' * 65), isFalse);
    });

    test('rejects spaces, dots, at-signs and non-ASCII letters', () {
      expect(isValidUsername('ab cd'), isFalse);
      expect(isValidUsername('ab.cd'), isFalse);
      expect(isValidUsername('ab@cd'), isFalse);
      expect(isValidUsername('zoë_x'), isFalse);
    });
  });

  group('isValidEmail', () {
    test('accepts a plain address', () {
      expect(isValidEmail('name@example.com'), isTrue);
      expect(isValidEmail('first.last+tag@sub.example.co'), isTrue);
    });

    test('rejects a missing at-sign or domain dot', () {
      expect(isValidEmail('nameexample.com'), isFalse);
      expect(isValidEmail('name@example'), isFalse);
    });

    test('rejects empty local or domain parts', () {
      expect(isValidEmail('@example.com'), isFalse);
      expect(isValidEmail('name@.com'), isFalse);
      expect(isValidEmail('name@example.'), isFalse);
    });

    test('rejects whitespace and repeated at-signs', () {
      expect(isValidEmail('na me@example.com'), isFalse);
      expect(isValidEmail(' name@example.com'), isFalse);
      expect(isValidEmail('a@@example.com'), isFalse);
    });
  });

  group('passwordProblems', () {
    test('a compliant password has no problems', () {
      expect(passwordProblems('Sunrise#42', minLength: 8), isEmpty);
    });

    test('reports the length rule with the configured minimum', () {
      expect(passwordProblems('Aa1!', minLength: 8), ['at least 8 characters']);
      expect(passwordProblems('Aa1!aaaa', minLength: 10), [
        'at least 10 characters',
      ]);
    });

    test('reports a missing uppercase letter', () {
      expect(passwordProblems('sunrise#42', minLength: 8), [
        'an uppercase letter',
      ]);
    });

    test('reports a missing lowercase letter', () {
      expect(passwordProblems('SUNRISE#42', minLength: 8), [
        'a lowercase letter',
      ]);
    });

    test('reports a missing number', () {
      expect(passwordProblems('Sunrise#pm', minLength: 8), ['a number']);
    });

    test('reports a missing special character', () {
      expect(passwordProblems('Sunrise42x', minLength: 8), [
        'a special character',
      ]);
    });

    test('accepts every special character Clerk allows', () {
      for (final ch in clerkPasswordSpecialChars.split('')) {
        expect(
          passwordProblems('Sunrise4$ch', minLength: 8),
          isEmpty,
          reason: 'special char $ch',
        );
      }
    });

    test('a space is not a special character', () {
      expect(passwordProblems('Sunrise 42', minLength: 8), [
        'a special character',
      ]);
    });

    test('lists every unmet rule in order when nothing is met', () {
      expect(passwordProblems('', minLength: 8), [
        'at least 8 characters',
        'an uppercase letter',
        'a lowercase letter',
        'a number',
        'a special character',
      ]);
    });
  });

  group('issueFromClerkError', () {
    test('identifier exists maps to email with a sign-in offer', () {
      final issue = issueFromClerkError(_clerkError('form_identifier_exists'));
      expect(issue.field, AccountField.email);
      expect(issue.offerSignIn, isTrue);
      expect(issue.offerCreate, isFalse);
      expect(issue.message, contains('already exists'));
    });

    test('identifier not found maps to email with a create offer', () {
      final issue = issueFromClerkError(
        _clerkError('form_identifier_not_found'),
      );
      expect(issue.field, AccountField.email);
      expect(issue.offerCreate, isTrue);
      expect(issue.offerSignIn, isFalse);
    });

    test('username taken maps to username', () {
      final issue = issueFromClerkError(_clerkError('form_username_exists'));
      expect(issue.field, AccountField.username);
      expect(issue.message, 'That username is taken.');
    });

    test('invalid username maps to username with the format hint', () {
      final issue = issueFromClerkError(
        _clerkError('form_username_invalid_character'),
      );
      expect(issue.field, AccountField.username);
      expect(issue.message, 'Use 4–64 letters, numbers, _ or -.');
    });

    test('breached password maps to password', () {
      final issue = issueFromClerkError(_clerkError('form_password_pwned'));
      expect(issue.field, AccountField.password);
      expect(issue.message, contains('data breach'));
    });

    test('incorrect password maps to password', () {
      final issue = issueFromClerkError(_clerkError('form_password_incorrect'));
      expect(issue.field, AccountField.password);
      expect(issue.message, 'Incorrect password.');
    });

    test('server password policy errors map to password requirements', () {
      for (final code in [
        'form_password_length_too_short',
        'form_password_not_strong_enough',
        'form_password_validation_failed',
      ]) {
        final issue = issueFromClerkError(_clerkError(code));
        expect(issue.field, AccountField.password, reason: code);
        expect(
          issue.message,
          'Password does not meet the requirements.',
          reason: code,
        );
      }
    });

    test('incorrect or expired verification code maps to code', () {
      for (final code in [
        'form_code_incorrect',
        'verification_code_invalid',
        'verification_expired',
      ]) {
        final issue = issueFromClerkError(_clerkError(code));
        expect(issue.field, AccountField.code, reason: code);
        expect(issue.message, 'Code is incorrect or expired.', reason: code);
      }
    });

    test('an unknown code falls back to a form-level message', () {
      final issue = issueFromClerkError(_clerkError('something_new'));
      expect(issue.field, AccountField.form);
      expect(issue.offerSignIn, isFalse);
      expect(issue.offerCreate, isFalse);
    });

    test('a non-Clerk error falls back to a form-level message', () {
      final issue = issueFromClerkError(Exception('socket closed'));
      expect(issue.field, AccountField.form);
      expect(
        issue.message,
        'Something went wrong. Check your details and try again.',
      );
    });

    test(
      'identifier-exists takes precedence over password codes in one response',
      () {
        final issue = issueFromClerkError(
          _clerkError('form_password_pwned', 'form_identifier_exists'),
        );
        expect(issue.field, AccountField.email);
        expect(issue.offerSignIn, isTrue);
      },
    );
  });
}
