import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:flutter/material.dart';

import 'clerk_email_code_actions.dart';
import '../theme/karmi_colors.dart';
import '../widgets/karmi_card.dart';

/// Fields supported by the Karmi-owned account creation form.
List<String> unsupportedClerkSignUpFields(List<clerk.Field> missing) => missing
    .where(
      (field) => !{
        clerk.Field.emailAddress,
        clerk.Field.firstName,
        clerk.Field.lastName,
        clerk.Field.password,
      }.contains(field),
    )
    .map((field) => field.name)
    .toList(growable: false);

/// Karmi-owned presentation for Clerk's email-code sign-in and sign-up flow.
/// Identity, verification, and session handling remain with Clerk.
class ClerkSignInCard extends StatefulWidget {
  const ClerkSignInCard({super.key, this.actions});

  /// Optional test seam. Production obtains a Clerk-backed implementation.
  final ClerkEmailCodeActions? actions;

  @override
  State<ClerkSignInCard> createState() => _ClerkSignInCardState();
}

class _ClerkSignInCardState extends State<ClerkSignInCard> {
  final _email = TextEditingController();
  final _code = TextEditingController();
  final _firstName = TextEditingController();
  final _lastName = TextEditingController();
  final _password = TextEditingController();
  final _confirmPassword = TextEditingController();
  bool _creatingAccount = false;
  bool _awaitingCode = false;
  bool _working = false;
  bool _initializedFromMidSignUp = false;
  String? _error;
  String? _notice;

  ClerkEmailCodeActions _actions(BuildContext context) =>
      widget.actions ??
      ClerkSdkEmailCodeActions(ClerkAuth.of(context, listen: false), context);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initializedFromMidSignUp) {
      final actions = _actions(context);
      if (actions.isMidSignUp) {
        _initializedFromMidSignUp = true;
        _creatingAccount = true;
        final email = actions.signUpEmail;
        if (email != null && _email.text.isEmpty) {
          _email.text = email;
        }
      }
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    _firstName.dispose();
    _lastName.dispose();
    _password.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  static const _codeNotice =
      'Use the newest email; earlier codes no longer work.';
  static const _incorrectCodeMessage =
      'That code is incorrect or expired. Use the newest email from Clerk, or tap Resend code.';

  bool _isIncorrectOrExpiredCodeError(Object error) {
    final text = error.toString().toLowerCase();
    return text.contains('form_code_incorrect') ||
        text.contains('code_incorrect') ||
        text.contains('incorrect') ||
        text.contains('expired');
  }

  bool _isPwnedPasswordError(Object error) {
    if (error is clerk.ClerkError) {
      if (error.errors?.errors?.any(
            (e) =>
                e.code?.toLowerCase().contains('pwned') == true ||
                e.code?.toLowerCase().contains('breach') == true,
          ) ==
          true) {
        return true;
      }
    }
    final text = error.toString().toLowerCase();
    return text.contains('pwned') ||
        text.contains('breach') ||
        text.contains('hibp');
  }

  bool _isPasswordTooShortError(Object error) {
    if (error is clerk.ClerkError) {
      if (error.errors?.errors?.any(
            (e) =>
                e.code?.toLowerCase().contains('short') == true ||
                e.code?.toLowerCase().contains('length') == true,
          ) ==
          true) {
        return true;
      }
    }
    final text = error.toString().toLowerCase();
    return text.contains('form_password_length_too_short') ||
        text.contains('too_short') ||
        text.contains('too short') ||
        (text.contains('password') && text.contains('short')) ||
        (text.contains('password') && text.contains('at least'));
  }

  Future<void> _submit() async {
    if (_working) return;
    final actions = _actions(context);
    final email = _email.text.trim().isNotEmpty
        ? _email.text.trim()
        : (actions.signUpEmail ?? '');
    if (_creatingAccount && actions.legalConsentRequired) {
      setState(
        () => _error =
            'Account creation is unavailable until Karmi’s terms and privacy consent are configured.',
      );
      return;
    }
    if (_creatingAccount && !_awaitingCode) {
      final firstNameRequired =
          actions.firstNameRequired ||
          actions.signUpMissingFields.contains(clerk.Field.firstName);
      final lastNameRequired =
          actions.lastNameRequired ||
          actions.signUpMissingFields.contains(clerk.Field.lastName);
      if ((firstNameRequired && _firstName.text.trim().isEmpty) ||
          (lastNameRequired && _lastName.text.trim().isEmpty)) {
        setState(() => _error = 'Enter your first and last name.');
        return;
      }
    }
    if (email.isEmpty || (_awaitingCode && _code.text.trim().isEmpty)) {
      setState(
        () => _error = _awaitingCode
            ? 'Enter the verification code from your email.'
            : 'Enter your email address to continue.',
      );
      return;
    }
    if (_creatingAccount && !_awaitingCode) {
      final minLength = actions.passwordMinLength;
      if (_password.text.length < minLength) {
        setState(
          () => _error = 'Password must be at least $minLength characters.',
        );
        return;
      }
      if (_password.text != _confirmPassword.text) {
        setState(() => _error = 'Passwords do not match.');
        return;
      }
    }

    setState(() {
      _working = true;
      _error = null;
      _notice = null;
    });
    try {
      if (_awaitingCode) {
        final code = _code.text.trim();
        if (_creatingAccount) {
          await actions.verifySignUpCode(code, _showClerkError);
        } else {
          await actions.verifySignInCode(email, code, _showClerkError);
        }
        if (!mounted) return;
        if (_error != null) {
          // Keep the code screen on error, do not reset or send new code.
          return;
        }
        if (!actions.isSignedIn) {
          setState(() {
            _error =
                'This sign-in method is unavailable. Check the Clerk email-code settings.';
          });
        }
        return;
      }

      if (_creatingAccount) {
        await actions.signUp(
          email,
          _firstName.text.trim().isEmpty ? null : _firstName.text.trim(),
          _lastName.text.trim().isEmpty ? null : _lastName.text.trim(),
          null,
          _showSignUpError,
          password: _password.text.isEmpty ? null : _password.text,
          passwordConfirmation: _confirmPassword.text.isEmpty
              ? null
              : _confirmPassword.text,
        );
      } else {
        await actions.signIn(email, null, _showClerkError);
      }

      if (!mounted) return;
      final missingFields = _creatingAccount
          ? actions.signUpMissingFields
          : const <clerk.Field>[];
      final unsupportedFields = unsupportedClerkSignUpFields(missingFields);
      final verificationStarted = _creatingAccount
          ? actions.signUpAwaitingCode
          : actions.signInAwaitingCode;
      setState(() {
        _awaitingCode = verificationStarted;
        if (_error != null) {
          return;
        } else if (verificationStarted) {
          _notice = _codeNotice;
        } else if (unsupportedFields.isNotEmpty) {
          _error =
              'This Clerk sign-up requires fields Karmi does not support: ${unsupportedFields.join(', ')}.';
        } else if (missingFields.isNotEmpty) {
          _error = 'Complete the required account details, then continue.';
        } else if (!actions.isSignedIn) {
          _error =
              'This sign-in method is unavailable. Check the Clerk email-code settings.';
        }
      });
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _resend() async {
    final actions = _actions(context);
    setState(() {
      _working = true;
      _error = null;
      _notice = null;
    });
    try {
      await actions.resendCode(_showClerkError);
      if (mounted && _error == null) {
        setState(() => _notice = _codeNotice);
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  void _showClerkError(Object error) {
    if (mounted) {
      setState(() {
        if (_isIncorrectOrExpiredCodeError(error)) {
          _error = _incorrectCodeMessage;
        } else {
          _error = error.toString();
        }
      });
    }
  }

  void _showSignUpError(Object error) {
    if (mounted) {
      setState(() {
        final minLength = _actions(context).passwordMinLength;
        if (_isPwnedPasswordError(error)) {
          _error =
              'This password appears in a known data breach. Choose a different one.';
        } else if (_isPasswordTooShortError(error)) {
          _error = 'Password must be at least $minLength characters.';
        } else if (_isIncorrectOrExpiredCodeError(error)) {
          _error = _incorrectCodeMessage;
        } else {
          _error = error.toString();
        }
      });
    }
  }

  Future<void> _changeMode() async {
    await _actions(context).reset(_showClerkError);
    if (!mounted) return;
    setState(() {
      _creatingAccount = !_creatingAccount;
      _awaitingCode = false;
      _code.clear();
      _password.clear();
      _confirmPassword.clear();
      _error = null;
      _notice = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final theme = Theme.of(context);
    final actions = _actions(context);
    if (actions.isSignedIn) return const SizedBox.shrink();
    if (actions.isNotAvailable) {
      return const KarmiCard(
        child: Text(
          'Sign-in is temporarily unavailable. Check your connection and try again.',
        ),
      );
    }
    if (actions.supportsEmailCode == false) {
      return const KarmiCard(
        child: Text(
          'Email-code sign-in is not enabled. Enable email codes in Clerk, then try again.',
        ),
      );
    }

    return KarmiCard(
      padding: const EdgeInsets.all(20),
      semanticContainer: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            _awaitingCode
                ? 'Check your email'
                : (_creatingAccount ? 'Create your account' : 'Welcome back'),
            style: theme.textTheme.titleLarge,
          ),
          const SizedBox(height: 6),
          Text(
            _awaitingCode
                ? 'Enter the six-digit code sent to ${_email.text.trim()}.'
                : 'Sign in securely with your email. Karmi never sees your password.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: colors.mutedForeground,
            ),
          ),
          const SizedBox(height: 18),
          if (!_awaitingCode && _creatingAccount) ...[
            TextField(
              controller: _firstName,
              textCapitalization: TextCapitalization.words,
              autofillHints: const [AutofillHints.givenName],
              decoration: InputDecoration(
                labelText:
                    (actions.firstNameRequired ||
                        actions.signUpMissingFields.contains(
                          clerk.Field.firstName,
                        ))
                    ? 'First name (required)'
                    : 'First name (optional)',
              ),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _lastName,
              textCapitalization: TextCapitalization.words,
              autofillHints: const [AutofillHints.familyName],
              decoration: InputDecoration(
                labelText:
                    (actions.lastNameRequired ||
                        actions.signUpMissingFields.contains(
                          clerk.Field.lastName,
                        ))
                    ? 'Last name (required)'
                    : 'Last name (optional)',
              ),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
          ],
          if (!_awaitingCode)
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Email address',
                prefixIcon: Icon(Icons.mail_outline),
              ),
              textInputAction: _creatingAccount
                  ? TextInputAction.next
                  : TextInputAction.done,
              onSubmitted: _creatingAccount || _working
                  ? null
                  : (_) => _submit(),
            )
          else
            TextField(
              controller: _code,
              keyboardType: TextInputType.number,
              autofillHints: const [AutofillHints.oneTimeCode],
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Verification code',
                prefixIcon: Icon(Icons.verified_outlined),
              ),
              textInputAction: TextInputAction.done,
              onSubmitted: _working ? null : (_) => _submit(),
            ),
          if (!_awaitingCode && _creatingAccount) ...[
            const SizedBox(height: 12),
            TextField(
              controller: _password,
              obscureText: true,
              autofillHints: const [AutofillHints.newPassword],
              decoration: InputDecoration(
                labelText: 'Create a password',
                prefixIcon: const Icon(Icons.lock_outline),
                helperText: 'At least ${actions.passwordMinLength} characters.',
              ),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _confirmPassword,
              obscureText: true,
              autofillHints: const [AutofillHints.newPassword],
              decoration: const InputDecoration(
                labelText: 'Confirm password',
                prefixIcon: Icon(Icons.lock_outline),
              ),
              textInputAction: TextInputAction.done,
              onSubmitted: _working ? null : (_) => _submit(),
            ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(
              _error!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: colors.destructive,
              ),
            ),
          ],
          if (_notice != null) ...[
            const SizedBox(height: 12),
            Text(
              _notice!,
              style: theme.textTheme.bodySmall?.copyWith(color: colors.success),
            ),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _working ? null : _submit,
            child: Text(
              _working
                  ? 'Please wait…'
                  : _awaitingCode
                  ? 'Verify and continue'
                  : 'Continue',
            ),
          ),
          if (_awaitingCode) ...[
            TextButton(
              onPressed: _working ? null : _resend,
              child: const Text('Resend code'),
            ),
            TextButton(
              onPressed: _working
                  ? null
                  : () => setState(() {
                      _awaitingCode = false;
                      _code.clear();
                      _error = null;
                      _notice = null;
                    }),
              child: const Text('Use a different email'),
            ),
          ] else ...[
            const SizedBox(height: 4),
            TextButton(
              onPressed: _working ? null : _changeMode,
              child: Text(
                _creatingAccount
                    ? 'Already have an account? Sign in'
                    : 'New to Karmi? Create an account',
              ),
            ),
          ],
        ],
      ),
    );
  }
}
