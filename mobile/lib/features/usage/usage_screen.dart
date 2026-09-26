import 'package:flutter/material.dart';
import '../../api/karmi_api.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';

class UsageScreen extends StatefulWidget {
  final KarmiApi api;

  const UsageScreen({super.key, required this.api});

  @override
  State<UsageScreen> createState() => _UsageScreenState();
}

class _UsageScreenState extends State<UsageScreen> {
  Future<UsageView>? _usageFuture;

  @override
  void initState() {
    super.initState();
    _usageFuture = widget.api.getUsage();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<UsageView>(
      future: _usageFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        } else if (snapshot.hasError) {
          return Center(child: Text('Error: ${snapshot.error}'));
        } else if (!snapshot.hasData) {
          return const Center(child: Text('Usage unavailable'));
        }

        final usage = snapshot.data!;
        final colors = Theme.of(context).extension<KarmiColors>()!;

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Usage & Plan',
              style: Theme.of(context).textTheme.displaySmall,
            ),
            const SizedBox(height: 24),
            KarmiGlassContainer(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Plan: ${usage.planLabel}',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Used: ${usage.everydayUsed} / ${usage.everydayLimit}',
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                  const SizedBox(height: 8),
                  LinearProgressIndicator(
                    value: usage.everydayLimit > 0
                        ? usage.everydayUsed / usage.everydayLimit
                        : 0,
                    backgroundColor: colors.muted,
                    valueColor: AlwaysStoppedAnimation<Color>(colors.primary),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Resets at: ${usage.resetAt}',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: colors.mutedForeground,
                        ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            // Plan cards read-only list would go here
            Text(
              'Purchases unavailable',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: colors.mutedForeground,
                  ),
              textAlign: TextAlign.center,
            ),
          ],
        );
      },
    );
  }
}
