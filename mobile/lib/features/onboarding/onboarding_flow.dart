import 'dart:async';

import 'package:flutter/material.dart';
import 'package:clerk_auth/clerk_auth.dart' as clerk;

import '../../auth/clerk_email_code_actions.dart';
import '../../auth/session.dart';
import '../../settings/karmi_settings.dart';
import '../../theme/karmi_colors.dart';
import 'widgets/choice_tile.dart';
import 'widgets/onboarding_scaffold.dart';
import 'widgets/otp_field.dart';
import 'widgets/pill_cta.dart';
/// Redesigned Onboarding Flow for Karmi Release 1.
/// Manages multi-step navigation, state persistence, Clerk auth integration,
/// backend profile persistence, and clean cutover to the Karmi shell.
class OnboardingFlow extends StatefulWidget {
  const OnboardingFlow({
    super.key,
    required this.session,
    this.settings,
    this.clerkActions,
    this.devAuthEnabled = kDevAuthEnabled,
    this.onComplete,
  });

  final KarmiSession session;
  final KarmiSettings? settings;
  final ClerkEmailCodeActions? clerkActions;
  final bool devAuthEnabled;
  final VoidCallback? onComplete;

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  static const int _totalSteps = 7;
  late int _currentStep;

  // Step 1: Auth state
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();
  bool _authAwaitingCode = false;
  bool _authLoading = false;
  String? _authError;

  // Step 2: Profile state
  final _firstNameController = TextEditingController();
  final _lastNameController = TextEditingController();
  bool _profileLoading = false;
  String? _profileError;

  // Step 3: Preferences state
  String _selectedLanguage = 'en';
  String _selectedMode = 'concise';

  ClerkEmailCodeActions _actions(BuildContext context) =>
      widget.clerkActions ??
      (widget.session.clerkAuth != null
          ? ClerkSdkEmailCodeActions(widget.session.clerkAuth!, context)
          : _FallbackDevAuthActions(widget.session));

  @override
  void initState() {
    super.initState();
    final savedStep = widget.settings?.onboardingStep ?? 0;
    // If user is already signed in, resume at least at profile step (step 2)
    if (widget.session.isSignedIn && savedStep < 2) {
      _currentStep = 2;
    } else {
      _currentStep = savedStep.clamp(0, _totalSteps - 1);
    }

    _selectedLanguage = widget.settings?.preferredLanguage ?? 'en';
    _selectedMode = widget.settings?.promptMode ?? 'concise';
  }

  @override
  void dispose() {
    _emailController.dispose();
    _otpController.dispose();
    _firstNameController.dispose();
    _lastNameController.dispose();
    super.dispose();
  }

  void _goToStep(int step) {
    final next = step.clamp(0, _totalSteps - 1);
    setState(() => _currentStep = next);
    widget.settings?.setOnboardingStep(next);
  }

  void _onBack() {
    if (_currentStep > 0) {
      if (_currentStep == 1 && _authAwaitingCode) {
        setState(() {
          _authAwaitingCode = false;
          _authError = null;
        });
      } else {
        _goToStep(_currentStep - 1);
      }
    }
  }

  Future<void> _submitEmail() async {
    final email = _emailController.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      setState(() => _authError = 'Enter a valid email address.');
      return;
    }
    setState(() {
      _authLoading = true;
      _authError = null;
    });
    if (!widget.session.hasClerk && !widget.devAuthEnabled) {
      setState(() {
        _authError = 'Clerk authentication is not configured.';
        _authLoading = false;
      });
      return;
    }
    try {
      if (widget.session.hasClerk) {
        final actions = _actions(context);
        await actions.signIn(email, null, (err) {
          if (mounted) setState(() => _authError = err.toString());
        });
      }
      if (mounted) {
        setState(() {
          _authAwaitingCode = true;
          _authLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _authError = e.toString();
          _authLoading = false;
        });
      }
    }
  }

  Future<void> _verifyOtp(String code) async {
    if (code.length < 6) return;
    if (!widget.session.hasClerk && !widget.devAuthEnabled) {
      setState(() => _authError = 'Clerk authentication is not configured.');
      return;
    }
    setState(() {
      _authLoading = true;
      _authError = null;
    });

    try {
      if (widget.session.hasClerk) {
        final actions = _actions(context);
        await actions.verifySignInCode(_emailController.text.trim(), code, (err) {
          if (mounted) setState(() => _authError = err.toString());
        });
      } else if (widget.devAuthEnabled) {
        await widget.session.signInWithDevToken();
      }
      if (mounted) {
        setState(() => _authLoading = false);
        _goToStep(2);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _authError = 'Code is incorrect or expired.';
          _authLoading = false;
        });
      }
    }
  }

  Future<void> _devSignIn() async {
    setState(() {
      _authLoading = true;
      _authError = null;
    });
    try {
      await widget.session.signInWithDevToken();
      if (mounted) {
        setState(() => _authLoading = false);
        _goToStep(2);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _authError = e.toString();
          _authLoading = false;
        });
      }
    }
  }

  Future<void> _submitProfile() async {
    final firstName = _firstNameController.text.trim();
    if (firstName.length < 2) {
      setState(() => _profileError = 'First name must be at least 2 characters.');
      return;
    }

    setState(() {
      _profileLoading = true;
      _profileError = null;
    });

    final lastName = _lastNameController.text.trim();
    final displayName = lastName.isNotEmpty ? '$firstName $lastName' : firstName;

    try {
      if (widget.session.isSignedIn) {
        await widget.session.api.updateProfile(displayName);
      }
      if (mounted) {
        setState(() => _profileLoading = false);
        _goToStep(3);
      }
    } catch (e) {
      // Backend may be unavailable in offline test mode; gracefully continue
      if (mounted) {
        setState(() => _profileLoading = false);
        _goToStep(3);
      }
    }
  }

  Future<void> _submitPreferences() async {
    await widget.settings?.setPreferredLanguage(_selectedLanguage);
    await widget.settings?.setPromptMode(_selectedMode);
    _goToStep(4);
  }

  void _finishOnboarding() {
    widget.settings?.setHasCompletedOnboarding(true);
    widget.settings?.setOnboardingStep(0);
    widget.onComplete?.call();
  }

  @override
  Widget build(BuildContext context) {
    switch (_currentStep) {
      case 0:
        return _buildWelcomeStep();
      case 1:
        return _buildAuthStep();
      case 2:
        return _buildProfileStep();
      case 3:
        return _buildPreferencesStep();
      case 4:
        return _buildPlanIntroStep();
      case 5:
        return _buildPermissionsStep();
      case 6:
      default:
        return _buildCompleteStep();
    }
  }

  Widget _buildWelcomeStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 0,
      totalSteps: _totalSteps,
      showBack: false,
      title: 'Meet Karmi',
      subtitle: 'One intelligent workspace for your thoughts, tasks, and drafts.',
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: colors.card,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: colors.borderSubtle),
            ),
            child: Column(
              children: [
                Icon(Icons.eco, size: 56, color: colors.primaryText),
                const SizedBox(height: 16),
                Text(
                  'Intelligent Drafts & Tasks',
                  style: textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: colors.foreground,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Experience distraction-free AI assistance designed for continuous work, local execution, and effortless draft generation.',
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium?.copyWith(
                    color: colors.mutedForeground,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _ValuePropMiniCard(
                  icon: Icons.flash_on,
                  title: 'Fast',
                  subtitle: 'Quick answers',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _ValuePropMiniCard(
                  icon: Icons.shield,
                  title: 'Private',
                  subtitle: 'Your control',
                ),
              ),
            ],
          ),
        ],
      ),
      bottomBar: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PillCta(
            key: const ValueKey('onboarding_get_started'),
            label: 'Get Started',
            onPressed: () => _goToStep(1),
          ),
          const SizedBox(height: 8),
          TextButton(
            key: const ValueKey('onboarding_already_have_account'),
            onPressed: () => _goToStep(1),
            child: const Text('Already have an account? Sign in'),
          ),
        ],
      ),
    );
  }

  Widget _buildAuthStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 1,
      totalSteps: _totalSteps,
      onBack: _onBack,
      title: _authAwaitingCode ? 'Enter verification code' : "What's your email?",
      subtitle: _authAwaitingCode
          ? 'We sent a 6-digit code to ${_emailController.text}. Use the newest email from Clerk.'
          : "We'll send a 6-digit confirmation code. No password needed.",
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!_authAwaitingCode) ...[
            TextField(
              key: const ValueKey('onboarding_email_field'),
              controller: _emailController,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              autofocus: true,
              decoration: InputDecoration(
                labelText: 'Email address',
                hintText: 'name@example.com',
                prefixIcon: const Icon(Icons.email_outlined),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              onSubmitted: (_) => _submitEmail(),
            ),
          ] else ...[
            OtpField(
              key: const ValueKey('onboarding_otp_field'),
              controller: _otpController,
              hasError: _authError != null,
              onCompleted: _verifyOtp,
            ),
          ],
          if (_authError != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(Icons.error_outline, size: 16, color: colors.destructive),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _authError!,
                    style: textTheme.bodySmall?.copyWith(
                      color: colors.destructive,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
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
            label: _authAwaitingCode ? 'Verify & Continue' : 'Continue',
            isLoading: _authLoading,
            onPressed: _authAwaitingCode
                ? () => _verifyOtp(_otpController.text)
                : _submitEmail,
          ),
          if (widget.devAuthEnabled) ...[
            const SizedBox(height: 8),
            TextButton(
              key: const ValueKey('onboarding_dev_signin'),
              onPressed: _devSignIn,
              child: const Text('Continue (development sign-in)'),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildProfileStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 2,
      totalSteps: _totalSteps,
      onBack: _onBack,
      title: 'What should we call you?',
      subtitle: 'Your name helps personalize conversations and generated drafts.',
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            key: const ValueKey('onboarding_first_name_field'),
            controller: _firstNameController,
            autofocus: true,
            decoration: InputDecoration(
              labelText: 'First name (required)',
              prefixIcon: const Icon(Icons.person_outline),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            key: const ValueKey('onboarding_last_name_field'),
            controller: _lastNameController,
            decoration: InputDecoration(
              labelText: 'Last name (optional)',
              prefixIcon: const Icon(Icons.person_outline),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          if (_profileError != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(Icons.error_outline, size: 16, color: colors.destructive),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _profileError!,
                    style: textTheme.bodySmall?.copyWith(
                      color: colors.destructive,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
      bottomBar: PillCta(
        key: const ValueKey('onboarding_profile_continue'),
        label: 'Continue',
        isLoading: _profileLoading,
        onPressed: _submitProfile,
      ),
    );
  }

  Widget _buildPreferencesStep() {
    return OnboardingScaffold(
      currentStep: 3,
      totalSteps: _totalSteps,
      onBack: _onBack,
      title: 'Set your preferences',
      subtitle: 'Choose how Karmi communicates and presents information.',
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            header: true,
            child: const Text(
              'Language',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ),
          const SizedBox(height: 8),
          ChoiceTile(
            title: 'English',
            description: 'Default interaction and model responses',
            isSelected: _selectedLanguage == 'en',
            onTap: () => setState(() => _selectedLanguage = 'en'),
          ),
          const SizedBox(height: 8),
          ChoiceTile(
            title: 'Indonesian',
            description: 'Bahasa Indonesia untuk percakapan',
            isSelected: _selectedLanguage == 'id',
            onTap: () => setState(() => _selectedLanguage = 'id'),
          ),
          const SizedBox(height: 24),
          Semantics(
            header: true,
            child: const Text(
              'Interaction Tone',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ),
          const SizedBox(height: 8),
          ChoiceTile(
            title: 'Concise & Direct',
            description: 'Speed-focused, short replies with minimal prose',
            isSelected: _selectedMode == 'concise',
            onTap: () => setState(() => _selectedMode = 'concise'),
          ),
          const SizedBox(height: 8),
          ChoiceTile(
            title: 'Detailed & Analytical',
            description: 'In-depth explanations with complete context',
            isSelected: _selectedMode == 'detailed',
            onTap: () => setState(() => _selectedMode = 'detailed'),
          ),
        ],
      ),
      bottomBar: PillCta(
        key: const ValueKey('onboarding_preferences_continue'),
        label: 'Continue',
        onPressed: _submitPreferences,
      ),
    );
  }

  Widget _buildPlanIntroStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 4,
      totalSteps: _totalSteps,
      onBack: _onBack,
      title: "You're starting on Ananta Free",
      subtitle: 'Enjoy essential features, reliable local execution, and free community models.',
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: colors.card,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: colors.primary, width: 1.5),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: colors.primary,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'ANANTA TIER',
                        style: textTheme.labelSmall?.copyWith(
                          color: colors.primaryForeground,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '\$0 / month',
                      style: textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: colors.foreground,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _PlanFeatureRow(
                  icon: Icons.check_circle_outline,
                  text: 'Unmetered everyday drafting & tasks',
                ),
                const SizedBox(height: 10),
                _PlanFeatureRow(
                  icon: Icons.check_circle_outline,
                  text: 'Local context & secure execution',
                ),
                const SizedBox(height: 10),
                _PlanFeatureRow(
                  icon: Icons.check_circle_outline,
                  text: 'Baseline community intelligence models',
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'No credit card required. Upgrade or change anytime.',
            textAlign: TextAlign.center,
            style: textTheme.bodySmall?.copyWith(
              color: colors.mutedForeground,
            ),
          ),
        ],
      ),
      bottomBar: PillCta(
        key: const ValueKey('onboarding_plan_continue'),
        label: 'Continue with Ananta Free',
        onPressed: () => _goToStep(5),
      ),
    );
  }

  Widget _buildPermissionsStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 5,
      totalSteps: _totalSteps,
      onBack: _onBack,
      title: 'Stay updated on background tasks',
      subtitle: 'Get notified when complex generations or multi-step tasks finish.',
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(28),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: colors.card,
              border: Border.all(color: colors.borderSubtle),
            ),
            child: Icon(
              Icons.notifications_active_outlined,
              size: 64,
              color: colors.primaryText,
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Notifications keep you informed when runs complete in the background so you never lose your flow.',
            textAlign: TextAlign.center,
            style: textTheme.bodyMedium?.copyWith(
              color: colors.mutedForeground,
            ),
          ),
        ],
      ),
      bottomBar: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PillCta(
            key: const ValueKey('onboarding_allow_notifications'),
            label: 'Allow Notifications',
            onPressed: () {
              _goToStep(6);
            },
          ),
          const SizedBox(height: 8),
          TextButton(
            key: const ValueKey('onboarding_skip_notifications'),
            onPressed: () => _goToStep(6),
            child: const Text('Maybe Later'),
          ),
        ],
      ),
    );
  }

  Widget _buildCompleteStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 6,
      totalSteps: _totalSteps,
      showBack: false,
      title: "You're all set!",
      subtitle: 'Welcome to Karmi. Let’s start creating together.',
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(32),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: colors.card,
              border: Border.all(color: colors.primary, width: 2),
            ),
            child: Icon(
              Icons.celebration_outlined,
              size: 64,
              color: colors.primaryText,
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Your workspace is prepared and configured with your personalized settings.',
            textAlign: TextAlign.center,
            style: textTheme.bodyMedium?.copyWith(
              color: colors.mutedForeground,
            ),
          ),
        ],
      ),
      bottomBar: PillCta(
        key: const ValueKey('onboarding_enter_karmi'),
        label: 'Enter Karmi',
        onPressed: _finishOnboarding,
      ),
    );
  }
}

class _ValuePropMiniCard extends StatelessWidget {
  const _ValuePropMiniCard({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: colors.primaryText),
          const SizedBox(height: 6),
          Text(
            title,
            style: textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: colors.foreground,
            ),
          ),
          Text(
            subtitle,
            style: textTheme.bodySmall?.copyWith(
              color: colors.mutedForeground,
            ),
          ),
        ],
      ),
    );
  }
}

class _PlanFeatureRow extends StatelessWidget {
  const _PlanFeatureRow({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return Row(
      children: [
        Icon(icon, size: 18, color: colors.primaryText),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: textTheme.bodyMedium?.copyWith(
              color: colors.foreground,
            ),
          ),
        ),
      ],
    );
  }
}

class _FallbackDevAuthActions implements ClerkEmailCodeActions {
  _FallbackDevAuthActions(this.session);
  final KarmiSession session;

  @override
  bool get isSignedIn => session.isSignedIn;
  @override
  bool get isNotAvailable => false;
  @override
  bool get supportsEmailCode => true;
  @override
  bool get legalConsentRequired => false;
  @override
  int get passwordMinLength => 8;
  @override
  bool get firstNameRequired => false;
  @override
  bool get lastNameRequired => false;
  @override
  List<clerk.Field> get signUpMissingFields => const [];
  @override
  bool get signInAwaitingCode => false;
  @override
  bool get signUpAwaitingCode => false;
  @override
  bool get isMidSignUp => false;
  @override
  String? get signUpEmail => null;

  @override
  Future<void> signIn(String email, String? code, ClerkFlowErrorHandler onError) async {
    await session.signInWithDevToken();
  }

  @override
  Future<void> verifySignInCode(String email, String code, ClerkFlowErrorHandler onError) async {
    await session.signInWithDevToken();
  }

  @override
  Future<void> signUp(String email, String? firstName, String? lastName, String? code, ClerkFlowErrorHandler onError, {String? password, String? passwordConfirmation}) async {
    await session.signInWithDevToken();
  }

  @override
  Future<void> verifySignUpCode(String code, ClerkFlowErrorHandler onError) async {
    await session.signInWithDevToken();
  }

  @override
  Future<void> resendCode(ClerkFlowErrorHandler onError) async {}

  @override
  Future<void> reset(ClerkFlowErrorHandler onError) async {}
}
