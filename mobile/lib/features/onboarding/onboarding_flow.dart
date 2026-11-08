import 'dart:async';

import 'package:flutter/material.dart';

import '../../auth/clerk_email_code_actions.dart';
import '../../auth/session.dart';
import '../../settings/karmi_settings.dart';
import '../../theme/karmi_colors.dart';
import '../../widgets/money.dart';
import '../plans/plan_catalog.dart';
import 'widgets/account_auth_step.dart';
import 'widgets/choice_tile.dart';
import 'widgets/onboarding_scaffold.dart';
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
    this.requestNotificationPermission,
  });

  final KarmiSession session;
  final KarmiSettings? settings;
  final ClerkEmailCodeActions? clerkActions;
  final bool devAuthEnabled;
  final void Function(String? selectedPlanId)? onComplete;
  final Future<bool> Function()? requestNotificationPermission;

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  static const int _totalSteps = 4;
  late int _currentStep;
  // True when Welcome's "Already have an account?" opened the account step.
  bool _authStartsInSignIn = false;

  // Step 2: Plan chooser state
  List<PlanInfo> _plans = kPlans;
  String _selectedPlanId = 'ananta';

  // Step 3: Notification permission state
  bool _permissionLoading = false;

  ClerkEmailCodeActions? _actions(BuildContext context) =>
      widget.clerkActions ??
      (widget.session.clerkAuth != null
          ? ClerkSdkEmailCodeActions(widget.session.clerkAuth!, context)
          : null);

  @override
  void initState() {
    super.initState();
    final savedStep = widget.settings?.onboardingStep ?? 0;
    _currentStep = _resolveInitialStep(savedStep);
    widget.session.addListener(_onSessionChanged);
    _loadPlans();
  }

  @override
  void didUpdateWidget(OnboardingFlow oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.session != widget.session) {
      oldWidget.session.removeListener(_onSessionChanged);
      widget.session.addListener(_onSessionChanged);
    }
  }

  @override
  void dispose() {
    widget.session.removeListener(_onSessionChanged);
    super.dispose();
  }

  // Step 1 advances via AccountAuthStep.onSignedIn, which also carries the
  // sign-up name; jumping from it here would dispose the step mid-call.
  void _onSessionChanged() {
    if (!mounted) return;
    if (widget.session.isSignedIn) {
      if (_currentStep == 0) _goToStep(2);
    } else if (_currentStep >= 2) {
      _goToStep(0);
    }
  }

  int _resolveInitialStep(int savedStep) {
    if (widget.session.isSignedIn) {
      if (savedStep == 3) return 3;
      return 2;
    }
    return savedStep.clamp(0, 1);
  }

  Future<void> _loadPlans() async {
    try {
      final serverPlans = await widget.session.api.getPlans();
      if (!mounted) return;
      final planMap = {for (final p in serverPlans) p.id: p};
      setState(() {
        _plans = kPlans.map((k) {
          final s = planMap[k.id] ?? (k.id == 'part' ? planMap['parth'] : null);
          return PlanInfo(
            k.id,
            s?.label ?? k.label,
            s?.everydayLimit ?? k.everydayLimit,
            priceInr: s?.priceInr,
          );
        }).toList();
      });
    } catch (_) {}
  }

  void _goToStep(int step) {
    final next = step.clamp(0, _totalSteps - 1);
    setState(() => _currentStep = next);
    widget.settings?.setOnboardingStep(next);
  }

  void _onBack() {
    if (_currentStep == 3) {
      _goToStep(2);
    } else if (_currentStep == 1) {
      _goToStep(0);
    }
  }

  void _onSignedIn(AccountDetails? details) {
    if (details != null) {
      final lastName = details.lastName;
      final displayName = lastName == null || lastName.isEmpty
          ? details.firstName
          : '${details.firstName} $lastName';
      unawaited(() async {
        try {
          await widget.session.api.updateProfile(displayName);
        } catch (_) {}
      }());
    }
    if (mounted) _goToStep(2);
  }

  Future<void> _devSignIn() async {
    await widget.session.signInWithDevToken();
    if (mounted) _goToStep(2);
  }

  Future<void> _onAllowNotifications() async {
    if (_permissionLoading) return;
    if (mounted) {
      setState(() => _permissionLoading = true);
    }
    try {
      await widget.requestNotificationPermission?.call();
    } catch (_) {}
    await _finishOnboarding();
  }

  Future<void> _finishOnboarding() async {
    final onComplete = widget.onComplete;
    final upgradePlan = _selectedPlanId == 'ananta' ? null : _selectedPlanId;
    await widget.settings?.setHasCompletedOnboarding(true);
    await widget.settings?.setOnboardingStep(0);
    onComplete?.call(upgradePlan);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _currentStep == 0 || _currentStep == 2,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        _onBack();
      },
      child: _buildCurrentStep(),
    );
  }

  Widget _buildCurrentStep() {
    switch (_currentStep) {
      case 0:
        return _buildWelcomeStep();
      case 1:
        return _buildAuthStep();
      case 2:
        return _buildPlanChooserStep();
      case 3:
      default:
        return _buildPermissionsStep();
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
      subtitle:
          'One intelligent workspace for your thoughts, tasks, and drafts.',
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
            onPressed: () {
              _authStartsInSignIn = false;
              _goToStep(1);
            },
          ),
          const SizedBox(height: 8),
          TextButton(
            key: const ValueKey('onboarding_already_have_account'),
            onPressed: () {
              _authStartsInSignIn = true;
              _goToStep(1);
            },
            child: const Text('Already have an account? Sign in'),
          ),
        ],
      ),
    );
  }

  Widget _buildAuthStep() {
    return AccountAuthStep(
      // Rebuild state when the entry point changes so the mode is re-read.
      key: ValueKey('auth-${_authStartsInSignIn ? 'signin' : 'create'}'),
      startInSignIn: _authStartsInSignIn,
      actions: _actions(context),
      devAuthEnabled: widget.devAuthEnabled,
      totalSteps: _totalSteps,
      currentStep: 1,
      onBack: _onBack,
      onSignedIn: _onSignedIn,
      onDevSignIn: _devSignIn,
    );
  }

  IconData _planIcon(String id) {
    switch (id) {
      case 'ananta':
        return Icons.eco;
      case 'yanta':
        return Icons.flash_on;
      case 'trika':
        return Icons.auto_awesome;
      case 'part':
        return Icons.military_tech;
      default:
        return Icons.stars;
    }
  }

  String _planDescription(PlanInfo plan) {
    if (plan.id == 'ananta') {
      return 'Free • ${plan.everydayLimit} everyday messages/day';
    }
    if (plan.priceInr != null) {
      return '${formatInrRupees(plan.priceInr!.toDouble())} / month • ${plan.everydayLimit} everyday messages/day';
    }
    return 'Price unavailable • ${plan.everydayLimit} everyday messages/day';
  }

  Widget _buildPlanChooserStep() {
    return OnboardingScaffold(
      currentStep: 2,
      totalSteps: _totalSteps,
      showBack: false,
      title: 'Choose your plan',
      subtitle:
          'Start free with Ananta or choose a plan with more everyday messages.',
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final plan in _plans) ...[
            ChoiceTile(
              key: ValueKey('plan_choice_${plan.id}'),
              title: plan.id == 'ananta' ? '${plan.label} (Free)' : plan.label,
              description: _planDescription(plan),
              icon: Icon(_planIcon(plan.id)),
              isSelected: _selectedPlanId == plan.id,
              onTap: () => setState(() => _selectedPlanId = plan.id),
            ),
            const SizedBox(height: 10),
          ],
        ],
      ),
      bottomBar: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PillCta(
            key: const ValueKey('onboarding_plan_continue'),
            label: 'Continue',
            onPressed: () => _goToStep(3),
          ),
        ],
      ),
    );
  }

  Widget _buildPermissionsStep() {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;

    return OnboardingScaffold(
      currentStep: 3,
      totalSteps: _totalSteps,
      onBack: _onBack,
      title: 'Know when Karmi replies',
      subtitle:
          'Get a notification when a reply finishes while Karmi is in the background.',
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
            'You can turn this off any time in system settings.',
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
            isLoading: _permissionLoading,
            onPressed: _onAllowNotifications,
          ),
          const SizedBox(height: 8),
          TextButton(
            key: const ValueKey('onboarding_skip_notifications'),
            onPressed: _permissionLoading ? null : _finishOnboarding,
            child: const Text('Maybe Later'),
          ),
        ],
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
            style: textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: colors.foreground,
            ),
          ),
          Text(
            subtitle,
            style: textTheme.bodyMedium?.copyWith(
              color: colors.mutedForeground,
            ),
          ),
        ],
      ),
    );
  }
}
