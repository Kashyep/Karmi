import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../theme/karmi_colors.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../chat/status_chip.dart';
import '../plans/plan_catalog.dart';

/// Usage & plan (T4.1). Only real `UsageView` values are shown; without a
/// server answer every value reads "unavailable" (web-shell rule).
class UsageScreen extends StatefulWidget {
  const UsageScreen({super.key, required this.api});

  final KarmiApi api;

  @override
  State<UsageScreen> createState() => _UsageScreenState();
}

class _UsageScreenState extends State<UsageScreen> {
  UsageView? _usage;
  bool _loading = true;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final usage = await widget.api.getUsage();
      if (mounted) setState(() => _usage = usage);
    } on KarmiApiException {
      if (mounted) setState(() => _failed = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final usage = _usage;
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    return RefreshIndicator(
      onRefresh: _load,
      edgeOffset: MediaQuery.paddingOf(context).top,
      child: ListView(
        padding: karmiPageInsets(context),
        children: [
          const KarmiHeading('Usage & plan'),
          if (_failed) ...[
            ErrorBanner(
              icon: Icons.cloud_off,
              tone: ErrorTone.warning,
              title: 'Usage unavailable',
              message: "Karmi couldn't load your usage right now.",
              actionLabel: 'Retry',
              onAction: _load,
            ),
            const SizedBox(height: 16),
          ],
          KarmiCard(
            child: _loading && usage == null
                ? const KarmiLoader(label: 'Loading usage')
                : usage == null
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Current plan', style: text.titleMedium),
                      Text('Unavailable', style: text.bodyLarge),
                      const SizedBox(height: 12),
                      Text('Everyday messages', style: text.titleMedium),
                      Text('Unavailable', style: text.bodyLarge),
                      const SizedBox(height: 12),
                      Text('Resets', style: text.titleMedium),
                      Text('Unavailable', style: text.bodyLarge),
                    ],
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Current plan', style: text.titleMedium),
                      Text(usage.planLabel, style: text.displaySmall),
                      const SizedBox(height: 16),
                      UsageMeter(
                        used: usage.everydayUsed,
                        limit: usage.everydayLimit,
                      ),
                      const SizedBox(height: 16),
                      Text('Resets', style: text.titleMedium),
                      Text(
                        _formatDateTime(context, usage.resetAt),
                        style: text.bodyLarge,
                      ),
                      if (usage.synthetic) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Synthetic development account',
                          style: text.bodyMedium?.copyWith(
                            color: colors.mutedForeground,
                          ),
                        ),
                      ],
                    ],
                  ),
          ),
          const SizedBox(height: 24),
          Semantics(header: true, child: Text('Plans', style: text.titleLarge)),
          const SizedBox(height: 4),
          Text('Purchases unavailable', style: text.bodyMedium),
          const SizedBox(height: 12),
          for (final plan in kPlans) ...[
            PlanCard(plan: plan, isCurrent: plan.id == usage?.planId),
            const SizedBox(height: 12),
          ],
        ],
      ),
    );
  }
}

String _formatDateTime(BuildContext context, DateTime at) {
  final local = at.toLocal();
  final l10n = MaterialLocalizations.of(context);
  return '${l10n.formatMediumDate(local)}, '
      '${TimeOfDay.fromDateTime(local).format(context)}';
}

/// Everyday allowance meter: numbers + words + bar, never the bar alone.
class UsageMeter extends StatelessWidget {
  const UsageMeter({super.key, required this.used, required this.limit});

  final int used;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final fraction = limit > 0 ? (used / limit).clamp(0.0, 1.0) : 1.0;
    final left = (limit - used).clamp(0, limit);
    final status = used >= limit
        ? const StatusChip(
            label: 'Allowance reached',
            icon: Icons.block,
            tone: StatusTone.danger,
          )
        : fraction >= 0.8
        ? const StatusChip(
            label: 'Near limit',
            icon: Icons.warning_amber,
            tone: StatusTone.warning,
          )
        : const StatusChip(
            label: 'Available',
            icon: Icons.check_circle_outline,
            tone: StatusTone.success,
          );
    return Semantics(
      container: true,
      label: 'Everyday messages',
      value: '$used of $limit used, $left left',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Everyday messages', style: text.titleMedium),
          const SizedBox(height: 4),
          Text('$used of $limit used · $left left', style: text.bodyLarge),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(value: fraction, minHeight: 8),
          ),
          const SizedBox(height: 8),
          status,
        ],
      ),
    );
  }
}
