import 'package:flutter/material.dart';

import 'plan_catalog.dart';

/// Plan selection (T4.6): the four plans, read-only. Checkout is disabled.
class PlanSelectionScreen extends StatelessWidget {
  const PlanSelectionScreen({super.key, this.currentPlanId});

  final String? currentPlanId;

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
              'Compare plans. Purchases are unavailable in this build, so '
              'your plan cannot be changed here.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 16),
            for (final plan in kPlans) ...[
              PlanCard(plan: plan, isCurrent: plan.id == currentPlanId),
              const SizedBox(height: 12),
            ],
          ],
        ),
      ),
    );
  }
}
