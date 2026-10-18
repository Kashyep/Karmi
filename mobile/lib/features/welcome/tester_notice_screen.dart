import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';
import 'tester_notice.dart';

/// Screen presented to testers on first launch.
///
/// Users must acknowledge this notice before proceeding to the app.
class TesterNoticeScreen extends StatelessWidget {
  const TesterNoticeScreen({super.key, required this.onAcknowledge});

  final VoidCallback onAcknowledge;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(24),
              children: [
                Icon(Icons.info_outline, size: 48, color: colors.primaryText),
                const SizedBox(height: 16),
                Semantics(
                  header: true,
                  child: Text(
                    kTesterNoticeTitle,
                    style: text.headlineMedium,
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: colors.card,
                    borderRadius: BorderRadius.circular(KarmiShape.cardRadius),
                    border: Border.all(color: colors.borderSubtle),
                  ),
                  child: Text(
                    kTesterNoticeText,
                    style: text.bodyLarge?.copyWith(
                      color: colors.primaryText,
                      height: 1.5,
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: FilledButton(
                    onPressed: onAcknowledge,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                    ),
                    child: const Text('I Understand and Acknowledge'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
