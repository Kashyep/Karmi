import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../widgets/karmi_card.dart';
import '../chat/status_chip.dart';

/// Mirrors `src/daily_agent/plans.py` SYNTHETIC_POLICIES (display name and
/// everyday limit). There is no plan catalogue endpoint yet; these are
/// synthetic development values, not tariffs.
class PlanInfo {
  const PlanInfo(this.id, this.label, this.everydayLimit);

  final String id;
  final String label;
  final int everydayLimit;
}

const List<PlanInfo> kPlans = [
  PlanInfo('ananta', 'Ananta', 20),
  PlanInfo('yanta', 'Yanta', 100),
  PlanInfo('trika', 'Trika', 250),
  PlanInfo('part', 'Part', 500),
];

/// Read-only plan card. Purchasing is disabled (CLAUDE.md: no paid checkout).
class PlanCard extends StatelessWidget {
  const PlanCard({super.key, required this.plan, this.isCurrent = false});

  final PlanInfo plan;
  final bool isCurrent;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Semantics(
                header: true,
                child: Text(plan.label, style: text.titleLarge),
              ),
              if (isCurrent)
                const StatusChip(
                  label: 'Current plan',
                  icon: Icons.check_circle_outline,
                  tone: StatusTone.success,
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${plan.everydayLimit} everyday messages per day',
            style: text.bodyLarge,
          ),
          const SizedBox(height: 4),
          Text(
            'Synthetic development limit',
            style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(Icons.lock_outline, size: 18, color: colors.mutedForeground),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Purchases unavailable',
                  style: text.labelLarge?.copyWith(
                    color: colors.mutedForeground,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
