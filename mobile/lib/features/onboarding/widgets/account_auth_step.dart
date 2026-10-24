import 'dart:async';

import 'package:flutter/material.dart';

import '../../../auth/account_rules.dart';
import '../../../auth/clerk_email_code_actions.dart';
import '../../../theme/karmi_colors.dart';
import 'onboarding_scaffold.dart';
import 'otp_field.dart';
import 'pill_cta.dart';

/// Name details captured at sign-up, used to prefill the profile.
class AccountDetails {
  const AccountDetails({required this.firstName, this.lastName});

  final String firstName;
  final String? lastName;
}

enum _Mode { create, signIn }

/// Account step: create an account (names, username, email, password, then an
/// emailed code) or sign in with email or username and password. Clerk asks
/// for an email code only when it requires a second factor.
class AccountAuthStep extends StatefulWidget {
  const AccountAuthStep({
    super.key,
    required this.actions,
    required this.devAuthEnabled,
    required this.totalSteps,
    required this.currentStep,
    required this.onBack,
    required this.onSignedIn,
    required this.onDevSignIn,
    this.startInSignIn = false,
  });

  /// Opens the Sign in form instead of Create account (Welcome's
  /// "Already have an account?" link).
  final bool startInSignIn;

  /// Null when Clerk is not configured for this build.
  final ClerkEmailCodeActions? actions;
  final bool devAuthEnabled;
  final int totalSteps;
  final int currentStep;
  final VoidCallback onBack;

  /// Called once Clerk reports a session. [details] is set after sign-up.
  final void Function(AccountDetails? details) onSignedIn;
  final Future<void> Function() onDevSignIn;

  @override
  State<AccountAuthStep> createState() => _AccountAuthStepState();
}

class _AccountAuthStepState extends State<AccountAuthStep> {
  static const int _resendCooldownSeconds = 30;

  final _first = TextEditingController();
  final _last = TextEditingController();
  final _username = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();

  late _Mode _mode = widget.startInSignIn ? _Mode.signIn : _Mode.create;
  bool _awaitingCode = false;
  bool _busy = false;
  bool _showPassword = false;
  bool _offerSignIn = false;
  bool _offerCreate = false;
  final Map<AccountField, String> _errors = {};
  AccountDetails? _pendingDetails;
  int _cooldown = 0;
  Timer? _cooldownTimer;

  @override
  void dispose() {
    _cooldownTimer?.cancel();
    for (final c in [_first, _last, _username, _email, _password, _code]) {
      c.dispose();
    }
    super.dispose();
  }

  void _startCooldown() {
    _cooldownTimer?.cancel();
    setState(() => _cooldown = _resendCooldownSeconds);
    _cooldownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return timer.cancel();
      setState(() => _cooldown -= 1);
      if (_cooldown <= 0) timer.cancel();
    });
  }

  void _clearErrors() {
    _errors.clear();
    _offerSignIn = false;
    _offerCreate = false;
  }

  void _onClerkError(Object error) {
    final issue = issueFromClerkError(error);
    if (!mounted) return;
    setState(() {
      _errors[issue.field] = issue.message;
      _offerSignIn = issue.offerSignIn;
      _offerCreate = issue.offerCreate;
    });
  }

  /// Runs one Clerk call with the busy flag, then applies the outcome.
  Future<void> _run(Future<void> Function(ClerkEmailCodeActions) op) async {
    final actions = widget.actions;
    if (actions == null) return;
    setState(() {
      _busy = true;
      _clearErrors();
    });
    try {
      await op(actions);
    } catch (e) {
      _onClerkError(e);
    }
    if (!mounted) return;
    setState(() => _busy = false);
    if (actions.isSignedIn) {
      widget.onSignedIn(_mode == _Mode.create ? _pendingDetails : null);
    }
  }

  Future<void> _submit() async {
    if (_busy) return;
    final actions = widget.actions;
    if (actions == null) {
      setState(() {
        _clearErrors();
        _errors[AccountField.form] = 'Clerk authentication is not configured.';
      });
      return;
    }
    if (_awaitingCode) return _verifyCode();

    final email = _email.text.trim();
    final password = _password.text;

    if (_mode == _Mode.signIn) {
      if (email.isEmpty || password.isEmpty) {
        setState(() {
          _clearErrors();
          _errors[AccountField.form] = 'Enter your email or username and password.';
        });
        return;
      }
      await _run((a) => a.signIn(
            identifier: email,
            password: password,
            onError: _onClerkError,
          ));
      if (mounted && !actions.isSignedIn && actions.signInAwaitingCode) {
        setState(() => _awaitingCode = true);
        _startCooldown();
      }
      return;
    }

    final first = _first.text.trim();
    final last = _last.text.trim();
    final username = _username.text.trim();
    final problems = passwordProblems(password, minLength: actions.passwordMinLength);
    setState(() {
      _clearErrors();
      if (first.length < 2) {
        _errors[AccountField.form] = 'First name must be at least 2 characters.';
      }
      if (!isValidUsername(username)) {
        _errors[AccountField.username] = 'Use 4–64 letters, numbers, _ or -.';
      }
      if (!isValidEmail(email)) {
        _errors[AccountField.email] = 'Enter a valid email address.';
      }
      if (problems.isNotEmpty) {
        _errors[AccountField.password] = 'Password needs ${problems.join(', ')}.';
      }
    });
    if (_errors.isNotEmpty) return;

    _pendingDetails = AccountDetails(
      firstName: first,
      lastName: last.isEmpty ? null : last,
    );
    await _run((a) => a.signUp(
          email: email,
          firstName: first,
          lastName: last.isEmpty ? null : last,
          username: username,
          password: password,
          onError: _onClerkError,
        ));
    if (!mounted || _errors.isNotEmpty || actions.isSignedIn) return;
    if (actions.signUpAwaitingCode) {
      setState(() => _awaitingCode = true);
      _startCooldown();
    } else {
      final missing = actions.signUpMissingFields.map((f) => f.name).join(', ');
      setState(() {
        _errors[AccountField.form] = missing.isEmpty
            ? 'Could not start sign-up. Try again.'
            : 'Clerk still needs: $missing.';
      });
    }
  }

  Future<void> _verifyCode() async {
    final code = _code.text;
    if (code.length != 6) {
      setState(() => _errors[AccountField.code] = 'Enter the 6-digit code.');
      return;
    }
    final isCreate = _mode == _Mode.create;
    final email = _email.text.trim();
    await _run((a) => isCreate
        ? a.verifySignUpCode(code, _onClerkError)
        : a.verifySignInCode(email, code, _onClerkError));
  }

  Future<void> _resend() async {
    if (_cooldown > 0 || _busy) return;
    await _run((a) => a.resendCode(_onClerkError));
    if (mounted && _errors.isEmpty) _startCooldown();
  }

  void _changeDetails() {
    setState(() {
      _awaitingCode = false;
      _code.clear();
      _clearErrors();
      _cooldownTimer?.cancel();
      _cooldown = 0;
    });
  }

  void _switchMode(_Mode mode) {
    setState(() {
      _mode = mode;
      _clearErrors();
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final isCreate = _mode == _Mode.create;
    final email = _email.text.trim();

    final title = _awaitingCode
        ? 'Enter verification code'
        : isCreate
        ? 'Create your account'
        : 'Welcome back';
    final subtitle = _awaitingCode
        ? 'We sent a 6-digit code to $email. Use the newest email from Clerk.'
        : isCreate
        ? 'Choose a username and password. We will email you a code to confirm your address.'
        : 'Sign in with your email or username and password.';

    return OnboardingScaffold(
      currentStep: widget.currentStep,
      totalSteps: widget.totalSteps,
      onBack: _awaitingCode ? _changeDetails : widget.onBack,
      title: title,
      subtitle: subtitle,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_awaitingCode) ...[
            OtpField(
              key: const ValueKey('onboarding_otp_field'),
              controller: _code,
              hasError: _errors[AccountField.code] != null,
              onCompleted: (_) => _verifyCode(),
            ),
            if (_errors[AccountField.code] != null)
              _ErrorText(_errors[AccountField.code]!),
            const SizedBox(height: 12),
            Row(
              children: [
                TextButton(
                  key: const ValueKey('onboarding_resend_code'),
                  onPressed: _cooldown > 0 || _busy ? null : _resend,
                  child: Text(
                    _cooldown > 0 ? 'Resend in ${_cooldown}s' : 'Resend code',
                  ),
                ),
                const Spacer(),
                TextButton(
                  key: const ValueKey('onboarding_change_details'),
                  onPressed: _changeDetails,
                  child: const Text('Change details'),
                ),
              ],
            ),
          ] else ...[
            if (isCreate) ...[
              _field(
                key: 'onboarding_first_name_field',
                controller: _first,
                label: 'First name',
                autofocus: true,
              ),
              const SizedBox(height: 12),
              _field(
                key: 'onboarding_last_name_field',
                controller: _last,
                label: 'Last name (optional)',
              ),
              const SizedBox(height: 12),
              _field(
                key: 'onboarding_username_field',
                controller: _username,
                label: 'Username',
                hint: '4–64 letters, numbers, _ or -',
                error: _errors[AccountField.username],
              ),
              const SizedBox(height: 12),
            ],
            _field(
              key: 'onboarding_email_field',
              controller: _email,
              label: isCreate ? 'Email address' : 'Email or username',
              hint: isCreate ? 'name@example.com' : null,
              keyboardType: TextInputType.emailAddress,
              error: _errors[AccountField.email],
              autofocus: !isCreate,
            ),
            const SizedBox(height: 12),
            TextField(
              key: const ValueKey('onboarding_password_field'),
              controller: _password,
              obscureText: !_showPassword,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: 'Password',
                helperText: isCreate
                    ? '8+ characters with uppercase, lowercase, a number and a symbol.'
                    : null,
                helperStyle: _supportStyle(context),
                helperMaxLines: 2,
                errorText: _errors[AccountField.password],
                errorStyle: _supportStyle(context, error: true),
                errorMaxLines: 3,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                suffixIcon: IconButton(
                  key: const ValueKey('onboarding_password_visibility'),
                  tooltip: _showPassword ? 'Hide password' : 'Show password',
                  icon: Icon(
                    _showPassword ? Icons.visibility_off : Icons.visibility,
                  ),
                  onPressed: () =>
                      setState(() => _showPassword = !_showPassword),
                ),
              ),
              onSubmitted: (_) => _submit(),
            ),
          ],
          if (!_awaitingCode && _errors[AccountField.form] != null) ...[
            _ErrorText(_errors[AccountField.form]!),
          ],
          if (_offerSignIn) ...[
            const SizedBox(height: 8),
            TextButton(
              key: const ValueKey('onboarding_offer_sign_in'),
              onPressed: () => _switchMode(_Mode.signIn),
              child: const Text('Sign in instead'),
            ),
          ],
          if (_offerCreate) ...[
            const SizedBox(height: 8),
            TextButton(
              key: const ValueKey('onboarding_offer_create'),
              onPressed: () => _switchMode(_Mode.create),
              child: const Text('Create an account'),
            ),
          ],
          if (!_awaitingCode) ...[
            const SizedBox(height: 12),
            TextButton(
              key: const ValueKey('onboarding_toggle_mode'),
              onPressed: () =>
                  _switchMode(isCreate ? _Mode.signIn : _Mode.create),
              child: Text(
                isCreate
                    ? 'Already have an account? Sign in'
                    : 'New to Karmi? Create an account',
                style: textTheme.bodyMedium?.copyWith(color: colors.primaryText),
              ),
            ),
          ],
        ],
      ),
      bottomBar: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PillCta(
            key: const ValueKey('onboarding_auth_continue'),
            label: _awaitingCode
                ? 'Verify & Continue'
                : isCreate
                ? 'Create account'
                : 'Sign in',
            isLoading: _busy,
            onPressed: _submit,
          ),
          if (widget.devAuthEnabled) ...[
            const SizedBox(height: 8),
            TextButton(
              key: const ValueKey('onboarding_dev_signin'),
              onPressed: widget.onDevSignIn,
              child: const Text('Continue (development sign-in)'),
            ),
          ],
        ],
      ),
    );
  }

  Widget _field({
    required String key,
    required TextEditingController controller,
    required String label,
    String? hint,
    String? error,
    bool autofocus = false,
    TextInputType? keyboardType,
  }) {
    return TextField(
      key: ValueKey(key),
      controller: controller,
      keyboardType: keyboardType,
      autocorrect: false,
      autofocus: autofocus,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        errorText: error,
        errorStyle: _supportStyle(context, error: true),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      ),
      onSubmitted: (_) => _submit(),
    );
  }

  // Helper/error text must use a text slot the Karmi theme defines (bodyMedium);
  // the default bodySmall slot is undefined and renders as missing glyphs.
  TextStyle? _supportStyle(BuildContext context, {bool error = false}) {
    final colors = KarmiColors.of(context);
    return Theme.of(context).textTheme.bodyMedium?.copyWith(
      fontSize: 12,
      color: error ? colors.destructive : colors.mutedForeground,
    );
  }
}

class _ErrorText extends StatelessWidget {
  const _ErrorText(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Row(
        children: [
          Icon(Icons.error_outline, size: 16, color: colors.destructive),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: textTheme.bodyMedium?.copyWith(
                color: colors.destructive,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
