import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../../theme/karmi_colors.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../../widgets/money.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';

const Duration kMonitorInterval = Duration(seconds: 5);

/// Live platform metrics. Refreshes every [kMonitorInterval] while the app is
/// resumed; pauses in the background and refreshes immediately on resume. A
/// failed refresh keeps the last good data on screen behind a banner.
class MonitorScreen extends StatefulWidget {
  const MonitorScreen({
    super.key,
    required this.controller,
    this.clock = DateTime.now,
  });

  final AdminController controller;

  /// Source of the "Updated" timestamp; injectable for goldens.
  final DateTime Function() clock;

  @override
  State<MonitorScreen> createState() => _MonitorScreenState();
}

class _MonitorScreenState extends State<MonitorScreen>
    with WidgetsBindingObserver {
  AdminMonitor? _data;
  Object? _error;
  DateTime? _updatedAt;
  Timer? _timer;
  bool _inFlight = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final state = SchedulerBinding.instance.lifecycleState;
    if (state == null || state == AppLifecycleState.resumed) _start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _start();
    } else {
      _stop();
    }
  }

  void _start() {
    _timer?.cancel();
    _timer = Timer.periodic(kMonitorInterval, (_) => _refresh());
    _refresh();
  }

  void _stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _refresh() async {
    if (_inFlight || !mounted) return;
    _inFlight = true;
    try {
      final monitor = await runAdminCall(
        widget.controller,
        (api, token) => api.monitor(token),
      );
      if (!mounted) return;
      setState(() {
        _data = monitor;
        _updatedAt = widget.clock();
        _error = null;
      });
    } on AdminException catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      _inFlight = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return ListView(
      padding: kAdminPagePadding,
      children: [
        Row(
          children: [
            Expanded(
              child: Semantics(
                liveRegion: true,
                child: Text(
                  _updatedAt == null
                      ? 'Waiting for first update'
                      : 'Updated ${formatAdminTime(context, _updatedAt!)}',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Refresh now',
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              onPressed: _refresh,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        if (_error != null) ...[
          const SizedBox(height: 8),
          ErrorBanner(
            icon: Icons.cloud_off,
            tone: data == null ? ErrorTone.danger : ErrorTone.warning,
            title: data == null
                ? "Couldn't load metrics"
                : 'Showing last known data',
            message: adminErrorMessage(_error!),
            actionLabel: 'Retry',
            onAction: _refresh,
          ),
        ],
        const SizedBox(height: 12),
        if (data == null && _error == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: KarmiLoader(label: 'Loading metrics'),
          )
        else if (data != null) ...[
          _metricGrid(data),
          const SizedBox(height: 12),
          _models(data.modelHealth),
          const SizedBox(height: 12),
          _providers(data.providerHealth),
        ],
      ],
    );
  }

  Widget _metricGrid(AdminMonitor m) {
    final cards = <_Metric>[
      _Metric('Active users', m.activeUsers?.toString() ?? kAdminUnavailable),
      _Metric(
        'Active streams',
        m.activeStreams?.toString() ?? kAdminUnavailable,
      ),
      _Metric(
        'Requests per minute',
        m.reqPerMin == null
            ? kAdminUnavailable
            : m.reqPerMin!.toStringAsFixed(1),
      ),
      _Metric(
        'Error rate',
        m.errorRate == null
            ? kAdminUnavailable
            : '${(m.errorRate! * 100).toStringAsFixed(2)}%',
      ),
      _Metric(
        'p95 latency',
        m.p95LatencyMs == null
            ? kAdminUnavailable
            : '${m.p95LatencyMs!.round()} ms',
      ),
      _Metric(
        'Spend today',
        m.spendTodayInr == null || m.platformBudgetInr == null
            ? kAdminUnavailable
            : '${formatInrRupees(m.spendTodayInr!)} of ${formatInrRupees(m.platformBudgetInr!)}',
      ),
      _Metric(
        'Requests today',
        m.requestsToday == null
            ? kAdminUnavailable
            : (m.dailyRequestCap == null
                  ? '${m.requestsToday}'
                  : '${m.requestsToday} of ${m.dailyRequestCap}'),
      ),
      _Metric(
        'Success rate',
        m.successRate == null
            ? kAdminUnavailable
            : '${(m.successRate! * 100).toStringAsFixed(1)}%',
      ),
      _Metric(
        'Open bug reports',
        m.openBugReports?.toString() ?? kAdminUnavailable,
      ),
      _Metric(
        'Cost today',
        m.costTodayInr == null
            ? kAdminUnavailable
            : formatInrRupees(m.costTodayInr!),
      ),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 12.0;
        final columns = constraints.maxWidth >= 600 ? 3 : 1;
        final width = (constraints.maxWidth - gap * (columns - 1)) / columns;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final c in cards)
              SizedBox(
                width: width,
                child: _MetricCard(metric: c),
              ),
          ],
        );
      },
    );
  }

  Widget _providers(List<ProviderHealth> providers) {
    final text = Theme.of(context).textTheme;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Providers', style: text.titleMedium),
          const SizedBox(height: 8),
          if (providers.isEmpty)
            Text(kAdminUnavailable, style: text.bodyMedium)
          else
            for (final p in providers) _ProviderRow(health: p),
        ],
      ),
    );
  }

  Widget _models(List<ModelHealth> models) {
    final text = Theme.of(context).textTheme;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Models', style: text.titleMedium),
          const SizedBox(height: 8),
          if (models.isEmpty)
            Text(kAdminUnavailable, style: text.bodyMedium)
          else
            for (final m in models) _ModelRow(health: m),
        ],
      ),
    );
  }
}

class _Metric {
  const _Metric(this.label, this.value);

  final String label;
  final String value;
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.metric});

  final _Metric metric;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Semantics(
      label: '${metric.label}: ${metric.value}',
      excludeSemantics: true,
      child: KarmiCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(metric.label, style: text.bodyMedium),
            const SizedBox(height: 4),
            Text(metric.value, style: text.headlineSmall),
          ],
        ),
      ),
    );
  }
}

class _ProviderRow extends StatelessWidget {
  const _ProviderRow({required this.health});

  final ProviderHealth health;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    final (word, icon, color) = switch (health.status.toLowerCase()) {
      'ok' ||
      'healthy' ||
      'up' => ('OK', Icons.check_circle_outline, colors.success),
      'degraded' => (
        'Degraded',
        Icons.warning_amber_rounded,
        colors.foreground,
      ),
      'down' || 'error' => ('Down', Icons.error_outline, colors.destructive),
      _ => ('Unknown', Icons.help_outline, colors.mutedForeground),
    };
    return Semantics(
      label: '${health.provider}: $word',
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 8),
            Expanded(child: Text(health.provider, style: text.bodyLarge)),
            const SizedBox(width: 8),
            Text(word, style: text.labelLarge?.copyWith(color: color)),
          ],
        ),
      ),
    );
  }
}

class _ModelRow extends StatelessWidget {
  const _ModelRow({required this.health});

  final ModelHealth health;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    final errorPct = health.errorRate == null
        ? kAdminUnavailable
        : '${(health.errorRate! * 100).toStringAsFixed(1)}%';
    final p50 = health.p50LatencyMs == null
        ? kAdminUnavailable
        : '${health.p50LatencyMs!.round()} ms';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${health.model} (${health.provider})',
                  style: text.bodyLarge?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              Text(
                '${health.runs} runs',
                style: text.labelMedium?.copyWith(
                  color: colors.mutedForeground,
                ),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            'Error rate: $errorPct · p50: $p50',
            style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
          ),
        ],
      ),
    );
  }
}
