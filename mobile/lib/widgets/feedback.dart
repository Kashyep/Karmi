import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';
import '../theme/karmi_theme.dart';

/// Shown only while a real request is pending (Design.md: no fake progress).
/// Under reduced motion it is a static icon plus the same text label.
class KarmiLoader extends StatelessWidget {
  const KarmiLoader({super.key, this.label = 'Working'});

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final reduceMotion = KarmiAccessibility.reduceMotionOf(context);
    return Semantics(
      liveRegion: true,
      label: label,
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox.square(
            dimension: 20,
            child: reduceMotion
                ? Icon(
                    Icons.hourglass_top,
                    size: 20,
                    color: colors.primary,
                    key: const ValueKey('karmi-loader-static'),
                  )
                : CircularProgressIndicator(
                    strokeWidth: 2.5,
                    key: const ValueKey('karmi-loader-spinner'),
                    color: colors.primary,
                  ),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: Text(label, style: Theme.of(context).textTheme.bodyMedium),
          ),
        ],
      ),
    );
  }
}

/// Trykker accent callout for empty screens.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.quote,
    this.body,
    this.icon = Icons.eco_outlined,
  });

  final String quote;
  final String? body;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 40, color: colors.primary),
          const SizedBox(height: 16),
          Text(
            quote,
            textAlign: TextAlign.center,
            style: KarmiText.of(context).quote,
          ),
          if (body != null) ...[
            const SizedBox(height: 8),
            Text(
              body!,
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: colors.mutedForeground),
            ),
          ],
        ],
      ),
    );
  }
}

/// Opaque banner for failed, offline, in-flight and limit-reached states.
/// Always an icon plus words; announced to screen readers.
class ErrorBanner extends StatelessWidget {
  const ErrorBanner({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.error_outline,
    this.actionLabel,
    this.onAction,
    this.tone = ErrorTone.danger,
  });

  final String title;
  final String message;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;
  final ErrorTone tone;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    final accent = switch (tone) {
      ErrorTone.danger => colors.destructive,
      ErrorTone.warning => colors.warning,
      ErrorTone.info => colors.primary,
    };
    return Semantics(
      container: true,
      liveRegion: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: colors.card,
          borderRadius: BorderRadius.circular(KarmiShape.controlRadius),
          border: Border.all(color: accent, width: 1.5),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Icon(icon, color: accent, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: text.titleMedium),
                    const SizedBox(height: 2),
                    Text(message, style: text.bodyMedium),
                    if (actionLabel != null && onAction != null) ...[
                      const SizedBox(height: 8),
                      OutlinedButton(
                        onPressed: onAction,
                        child: Text(actionLabel!),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

enum ErrorTone { danger, warning, info }
