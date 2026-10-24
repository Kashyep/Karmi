import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_tokens.dart';

/// Multi-step wrapper with animated progress bar, back navigation, safe-area management,
/// and scrollable content slot.
class OnboardingScaffold extends StatelessWidget {
  const OnboardingScaffold({
    super.key,
    required this.currentStep,
    required this.totalSteps,
    required this.body,
    this.bottomBar,
    this.onBack,
    this.showBack = true,
    this.isOffline = false,
    this.title,
    this.subtitle,
  });

  final int currentStep;
  final int totalSteps;
  final Widget body;
  final Widget? bottomBar;
  final VoidCallback? onBack;
  final bool showBack;
  final bool isOffline;
  final String? title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final progress = totalSteps > 0
        ? ((currentStep + 1) / totalSteps).clamp(0.0, 1.0)
        : 0.0;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            // Offline banner
            if (isOffline)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                color: colors.destructive,
                child: Row(
                  children: [
                    Icon(
                      Icons.cloud_off,
                      size: 16,
                      color: colors.destructiveForeground,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Offline. Reconnecting when internet is restored...',
                        style: textTheme.bodyMedium?.copyWith(
                          color: colors.destructiveForeground,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),

            // Navigation bar & Progress indicator
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Column(
                children: [
                  Row(
                    children: [
                      if (showBack && onBack != null)
                        IconButton(
                          key: const ValueKey('onboarding_back_button'),
                          icon: const Icon(Icons.arrow_back),
                          color: colors.foreground,
                          tooltip: 'Back',
                          onPressed: onBack,
                          iconSize: 24,
                          constraints: const BoxConstraints(
                            minWidth: 48,
                            minHeight: 48,
                          ),
                        )
                      else
                        const SizedBox(width: 48, height: 48),
                      Expanded(
                        child: Semantics(
                          liveRegion: true,
                          label: 'Step ${currentStep + 1} of $totalSteps',
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: AnimatedContainer(
                              duration: KarmiTokens.standard,
                              height: 6,
                              child: LinearProgressIndicator(
                                value: progress,
                                backgroundColor: colors.muted,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  colors.primary,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 48, height: 48),
                    ],
                  ),
                ],
              ),
            ),

            // Scrollable Content
            Expanded(
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(
                  parent: BouncingScrollPhysics(),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (title != null) ...[
                          Semantics(
                            header: true,
                            child: Text(
                              title!,
                              style: textTheme.headlineSmall?.copyWith(
                                color: colors.foreground,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          const SizedBox(height: 8),
                        ],
                        if (subtitle != null) ...[
                          Text(
                            subtitle!,
                            style: textTheme.bodyMedium?.copyWith(
                              color: colors.mutedForeground,
                            ),
                          ),
                          const SizedBox(height: 24),
                        ],
                        body,
                      ],
                    ),
                  ),
                ),
              ),
            ),

            // Bottom Bar / Action
            if (bottomBar != null)
              Container(
                padding: const EdgeInsets.all(24),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: bottomBar!,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
