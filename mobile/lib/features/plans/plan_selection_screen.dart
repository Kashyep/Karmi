import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import 'plan_catalog.dart';

/// Plan selection (T4.6): the four plans. Checkout is disabled; beta testers can
/// unlock a tier with an access code when [api] is provided.
class PlanSelectionScreen extends StatefulWidget {
  const PlanSelectionScreen({
    super.key,
    this.currentPlanId,
    this.api,
    this.onPlanChanged,
  });

  final String? currentPlanId;
  final KarmiApi? api;
  final Future<void> Function()? onPlanChanged;

  @override
  State<PlanSelectionScreen> createState() => _PlanSelectionScreenState();
}

class _PlanSelectionScreenState extends State<PlanSelectionScreen> {
  final _code = TextEditingController();
  String? _currentPlanId;
  String? _message;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _currentPlanId = widget.currentPlanId;
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _redeem() async {
    final api = widget.api;
    final code = _code.text.trim();
    if (api == null || code.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    String message;
    try {
      final result = await api.redeemAccessCode(code);
      message = result.changed
          ? 'Unlocked ${result.planLabel}. Enjoy the beta!'
          : 'You already have ${result.planLabel} or higher.';
      if (!mounted) return;
      setState(() => _currentPlanId = result.planId);
      _code.clear();
      await widget.onPlanChanged?.call();
    } on KarmiApiException catch (error) {
      message = error is NetworkException
          ? "Couldn't reach the server. Check your connection."
          : 'That code is not valid, or there were too many attempts. '
                'Wait a minute and check the code.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _message = message;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Plans')),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Compare plans. Purchases are unavailable in this beta. '
              'Every plan uses free models; higher plans get more usage and '
              'stronger model classes.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 16),
            if (widget.api != null) ...[
              TextField(
                key: const ValueKey('access-code-field'),
                controller: _code,
                enabled: !_busy,
                textCapitalization: TextCapitalization.characters,
                autocorrect: false,
                enableSuggestions: false,
                decoration: const InputDecoration(
                  labelText: 'Access code',
                  helperText:
                      'Have a beta access code? Enter it to unlock a plan.',
                  border: OutlineInputBorder(),
                ),
                onSubmitted: (_) => _redeem(),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton(
                  key: const ValueKey('access-code-apply'),
                  onPressed: _busy ? null : _redeem,
                  child: const Text('Apply code'),
                ),
              ),
              if (_message != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      _message!,
                      key: const ValueKey('access-code-message'),
                    ),
                  ),
                ),
              const SizedBox(height: 16),
            ],
            for (final plan in kPlans) ...[
              PlanCard(plan: plan, isCurrent: plan.id == _currentPlanId),
              const SizedBox(height: 12),
            ],
          ],
        ),
      ),
    );
  }
}
