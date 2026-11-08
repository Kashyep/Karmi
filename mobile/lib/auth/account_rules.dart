import 'package:clerk_auth/clerk_auth.dart' as clerk;

/// Characters Clerk accepts as the special-character class in passwords.
const String clerkPasswordSpecialChars = r'''!"#$%&'()*+,-./:;<=>?@[]^_`{|}~''';

final RegExp _usernamePattern = RegExp(r'^[A-Za-z0-9_-]{4,64}$');
final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

bool isValidUsername(String value) => _usernamePattern.hasMatch(value);

bool isValidEmail(String value) => _emailPattern.hasMatch(value);

/// Returns the unmet password rules, empty when the password passes the
/// local checks. Clerk's zxcvbn strength and breach checks run server-side and
/// come back as `form_password_*` errors.
List<String> passwordProblems(String password, {required int minLength}) {
  final problems = <String>[];
  if (password.length < minLength) {
    problems.add('at least $minLength characters');
  }
  if (!RegExp(r'[A-Z]').hasMatch(password)) {
    problems.add('an uppercase letter');
  }
  if (!RegExp(r'[a-z]').hasMatch(password)) {
    problems.add('a lowercase letter');
  }
  if (!RegExp(r'[0-9]').hasMatch(password)) {
    problems.add('a number');
  }
  final special = RegExp('[${RegExp.escape(clerkPasswordSpecialChars)}]');
  if (!special.hasMatch(password)) {
    problems.add('a special character');
  }
  return problems;
}

/// Which form field a Clerk failure belongs to.
enum AccountField { username, email, password, code, form }

class AccountIssue {
  const AccountIssue(
    this.field,
    this.message, {
    this.offerSignIn = false,
    this.offerCreate = false,
  });

  final AccountField field;
  final String message;
  final bool offerSignIn;
  final bool offerCreate;
}

/// True when a password-reset request failed because the account does not
/// exist or cannot use email-code reset. The UI treats this exactly like a
/// sent code so the form does not reveal which emails have accounts.
bool isResetUnavailableError(Object error) {
  return _clerkCodes(error).any(
    (c) =>
        c.contains('identifier_not_found') ||
        c.contains('strategy_for_user_invalid'),
  );
}

/// Maps a Clerk error to the field it belongs to, with a user-facing message.
AccountIssue issueFromClerkError(Object error) {
  final codes = _clerkCodes(error);
  bool has(String fragment) => codes.any((c) => c.contains(fragment));

  if (has('identifier_exists')) {
    return const AccountIssue(
      AccountField.email,
      'An account already exists for this email. Sign in instead.',
      offerSignIn: true,
    );
  }
  if (has('identifier_not_found')) {
    return const AccountIssue(
      AccountField.email,
      'No account found for that email or username. Create an account instead.',
      offerCreate: true,
    );
  }
  if (has('username') && (has('exists') || has('taken'))) {
    return const AccountIssue(AccountField.username, 'That username is taken.');
  }
  if (has('username')) {
    return const AccountIssue(
      AccountField.username,
      'Use 4–64 letters, numbers, _ or -.',
    );
  }
  if (has('pwned')) {
    return const AccountIssue(
      AccountField.password,
      'This password appears in a known data breach. Choose a different one.',
    );
  }
  if (has('password_incorrect')) {
    return const AccountIssue(AccountField.password, 'Incorrect password.');
  }
  if (has('password')) {
    return const AccountIssue(
      AccountField.password,
      'Password does not meet the requirements.',
    );
  }
  if (has('verification_code') || has('code_incorrect') || has('expired')) {
    return const AccountIssue(
      AccountField.code,
      'Code is incorrect or expired.',
    );
  }
  return const AccountIssue(
    AccountField.form,
    'Something went wrong. Check your details and try again.',
  );
}

List<String> _clerkCodes(Object error) {
  final codes = <String>[];
  if (error is clerk.ClerkError) {
    final list = error.errors?.errors ?? const [];
    for (final e in list) {
      final code = e.code;
      if (code != null) codes.add(code.toLowerCase());
    }
  }
  if (codes.isEmpty) codes.add(error.toString().toLowerCase());
  return codes;
}
