import 'dart:convert';

import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_tier.dart';
import '../../widgets/karmi_card.dart';
import '../../widgets/money.dart';
import '../chat/status_chip.dart';

/// Extension to fetch customer plans from the server (`/v1/plans`).
extension CustomerPlansApi on KarmiApi {
  Future<List<PlanView>> getPlans() async {
    final uri = Uri.parse('$baseUrl/v1/plans');
    final headers = <String, String>{};
    final provider = tokenProvider;
    final bearer = provider == null ? token : await provider();
    if (bearer != null) {
      headers['Authorization'] = 'Bearer $bearer';
    }
    final response = await client.get(uri, headers: headers).timeout(timeout);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is List) {
        return decoded
            .map((item) => PlanView.fromJson(item as Map<String, dynamic>))
            .toList();
      }
    }
    throw ServerException(response.statusCode);
  }
}

/// Mirrors `src/daily_agent/plans.py` SYNTHETIC_POLICIES (display name and
/// everyday limit). There is no plan catalogue endpoint yet; these are
/// synthetic development values, not tariffs.
class PlanInfo {
  const PlanInfo(this.id, this.label, this.everydayLimit, {this.priceInr});

  final String id;
  final String label;
  final int everydayLimit;
  final int? priceInr;
}

const List<PlanInfo> kPlans = [
  PlanInfo('ananta', 'Ananta', 20),
  PlanInfo('yanta', 'Yanta', 100),
  PlanInfo('trika', 'Trika', 250),
  PlanInfo('part', 'Parth', 500),
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
              if (KarmiTier.fromPlanId(plan.id) case final tier?)
                ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.asset(
                    'assets/app_icons/${tier.name}.webp',
                    width: 40,
                    height: 40,
                    excludeFromSemantics: true,
                  ),
                ),
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
          if (plan.priceInr != null) ...[
            const SizedBox(height: 6),
            Text(
              '${formatInrRupees(plan.priceInr!.toDouble())} / month',
              key: ValueKey('plan_price_${plan.id}'),
              style: text.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: colors.foreground,
              ),
            ),
          ],
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
