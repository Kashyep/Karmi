import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../theme/karmi_colors.dart';

enum StatusTone { success, info, warning, danger, neutral }

/// Icon + word + colour for every state (Design.md: never colour alone).
///
/// Text is always `--foreground` on `--muted`; the tone only colours the icon and
/// outline, and every tone colour is ≥4.5:1 on `--muted` in both themes, so
/// accent is never used as text on light surfaces (§2.4).
class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    required this.icon,
    required this.tone,
  });

  factory StatusChip.outcome(Outcome outcome, {Key? key}) {
    final (label, icon, tone) = outcomeStatus(outcome);
    return StatusChip(key: key, label: label, icon: icon, tone: tone);
  }

  factory StatusChip.task({required bool completed, Key? key}) => completed
      ? StatusChip(
          key: key,
          label: 'Completed',
          icon: Icons.check_circle_outline,
          tone: StatusTone.success,
        )
      : StatusChip(
          key: key,
          label: 'Open',
          icon: Icons.radio_button_unchecked,
          tone: StatusTone.neutral,
        );

  final String label;
  final IconData icon;
  final StatusTone tone;

  static Color toneColor(KarmiColors colors, StatusTone tone) => switch (tone) {
    StatusTone.success => colors.success,
    StatusTone.info => colors.primary,
    StatusTone.warning => colors.warning,
    StatusTone.danger => colors.destructive,
    StatusTone.neutral => colors.mutedForeground,
  };

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final toneColor = StatusChip.toneColor(colors, tone);
    return Semantics(
      label: 'Status: $label',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: colors.muted,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: toneColor),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: toneColor),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                style: Theme.of(
                  context,
                ).textTheme.labelSmall?.copyWith(color: colors.foreground),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Outcome → Design.md copy ("Awaiting confirmation", "Could not confirm completion", …).
(String, IconData, StatusTone) outcomeStatus(Outcome outcome) =>
    switch (outcome) {
      Outcome.accept => (
        'Completed',
        Icons.check_circle_outline,
        StatusTone.success,
      ),
      Outcome.repair => ('Corrected', Icons.auto_fix_high, StatusTone.info),
      Outcome.escalate => (
        'Needs review',
        Icons.manage_search,
        StatusTone.warning,
      ),
      Outcome.askUser => (
        'Awaiting confirmation',
        Icons.help_outline,
        StatusTone.warning,
      ),
      Outcome.safeStop => (
        'Could not confirm completion',
        Icons.report_gmailerrorred,
        StatusTone.danger,
      ),
      Outcome.deferred => ('Deferred', Icons.schedule, StatusTone.neutral),
      Outcome.unknown => (
        'Status unknown',
        Icons.help_center_outlined,
        StatusTone.neutral,
      ),
    };
