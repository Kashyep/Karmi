import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_motion.dart';
import '../../widgets/feedback.dart';
import '../chat/status_chip.dart';

/// Task confirmation sheet for `ASK_USER` replies (T4.7).
///
/// GAP: `MessageView` carries only free text. The backend sends no structured
/// action / target / date / timezone payload, so there is nothing that could be
/// confirmed safely. The sheet shows the reply verbatim, labels every required
/// field as not provided, and keeps Confirm disabled. The body is opaque.
Future<void> showTaskConfirmationSheet(
  BuildContext context,
  MessageView message,
) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    sheetAnimationStyle: AnimationStyle(
      duration: KarmiMotion.duration(context),
      reverseDuration: KarmiMotion.duration(context, KarmiMotion.fast),
    ),
    builder: (context) => TaskConfirmationSheet(message: message),
  );
}

class TaskConfirmationSheet extends StatelessWidget {
  const TaskConfirmationSheet({super.key, required this.message});

  final MessageView message;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    Widget field(String label) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 2, child: Text(label, style: text.labelLarge)),
          Expanded(
            flex: 3,
            child: Text(
              'Not provided',
              style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
            ),
          ),
        ],
      ),
    );

    return ColoredBox(
      color: colors.card,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Text('Confirm task', style: text.headlineSmall),
            ),
            const SizedBox(height: 8),
            StatusChip.outcome(message.outcome),
            const SizedBox(height: 12),
            Text(message.response, style: text.bodyLarge),
            const Divider(height: 32),
            field('Action'),
            field('Target'),
            field('Date and time'),
            field('Timezone'),
            const SizedBox(height: 16),
            const ErrorBanner(
              icon: Icons.info_outline,
              tone: ErrorTone.info,
              title: 'Missing details',
              message:
                  'Karmi can only confirm an action when the server sends its '
                  'exact details. Reply in chat with the missing information.',
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Close'),
                  ),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: FilledButton(onPressed: null, child: Text('Confirm')),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
