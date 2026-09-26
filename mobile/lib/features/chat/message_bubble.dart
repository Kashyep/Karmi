import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';
import '../../widgets/karmi_card.dart';
import 'chat_entry.dart';
import 'status_chip.dart';

/// A chat bubble on an opaque surface, capped to a readable line length.
class MessageBubble extends StatelessWidget {
  const MessageBubble.user({super.key, required UserEntry this.entry})
    : reply = null,
      announce = false,
      onReviewDetails = null;

  const MessageBubble.reply({
    super.key,
    required ReplyEntry this.reply,
    this.announce = false,
    this.onReviewDetails,
  }) : entry = null;

  final UserEntry? entry;
  final ReplyEntry? reply;

  /// Latest reply: exposed as a live region so screen readers announce it.
  final bool announce;

  /// Shown for `ASK_USER` replies; opens the task confirmation sheet.
  final VoidCallback? onReviewDetails;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    final isUser = entry != null;

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = math.min(
          constraints.maxWidth * 0.88,
          readableProseWidth(context),
        );
        final bubble = Container(
          constraints: BoxConstraints(maxWidth: maxWidth),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: isUser ? colors.primary : colors.card,
            borderRadius: BorderRadius.circular(KarmiShape.cardRadius),
            border: isUser ? null : Border.all(color: colors.borderSubtle),
          ),
          child: isUser
              ? Text(
                  entry!.text,
                  style: text.bodyLarge?.copyWith(
                    color: colors.primaryForeground,
                  ),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    StatusChip.outcome(reply!.message.outcome),
                    const SizedBox(height: 8),
                    Text(reply!.message.response, style: text.bodyLarge),
                    if (reply!.message.outcome == Outcome.askUser &&
                        onReviewDetails != null) ...[
                      const SizedBox(height: 4),
                      TextButton.icon(
                        onPressed: onReviewDetails,
                        icon: const Icon(Icons.fact_check_outlined),
                        label: const Text('Review details'),
                      ),
                    ],
                  ],
                ),
        );

        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Semantics(
              container: true,
              liveRegion: announce,
              label: isUser ? 'You said' : 'Karmi replied',
              child: bubble,
            ),
          ),
        );
      },
    );
  }
}
