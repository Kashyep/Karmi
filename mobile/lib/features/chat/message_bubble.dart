import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

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
      onReviewDetails = null,
      onFeedback = null,
      onSelectReason = null,
      onRegenerate = null;

  const MessageBubble.reply({
    super.key,
    required ReplyEntry this.reply,
    this.announce = false,
    this.onReviewDetails,
    this.onFeedback,
    this.onSelectReason,
    this.onRegenerate,
  }) : entry = null;

  final UserEntry? entry;
  final ReplyEntry? reply;

  /// Latest reply: exposed as a live region so screen readers announce it.
  final bool announce;

  /// Shown for `ASK_USER` replies; opens the task confirmation sheet.
  final VoidCallback? onReviewDetails;

  final ValueChanged<FeedbackRating>? onFeedback;
  final ValueChanged<String>? onSelectReason;
  final VoidCallback? onRegenerate;
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
                    MarkdownBody(
                      data: reply!.message.response,
                      styleSheet: _markdownStyle(context, colors, text),
                      selectable: false,
                      onTapLink: (text, href, title) {},
                      // Never fetch images named by a model reply; show the alt text.
                      imageBuilder: (uri, title, alt) => Text(
                        alt ?? '',
                        style: text.bodyLarge?.copyWith(
                          color: colors.mutedForeground,
                        ),
                      ),
                    ),
                    if (reply!.message.outcome == Outcome.askUser &&
                        onReviewDetails != null) ...[
                      const SizedBox(height: 4),
                      TextButton.icon(
                        onPressed: onReviewDetails,
                        icon: const Icon(Icons.fact_check_outlined),
                        label: const Text('Review details'),
                      ),
                    ],
                    const SizedBox(height: 4),
                    _ReplyActions(
                      reply: reply!,
                      onFeedback: onFeedback,
                      onSelectReason: onSelectReason,
                      onRegenerate: onRegenerate,
                    ),
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

MarkdownStyleSheet _markdownStyle(
  BuildContext context,
  KarmiColors colors,
  TextTheme text,
) {
  final bodyStyle =
      text.bodyLarge?.copyWith(color: colors.foreground) ??
      TextStyle(
        color: colors.foreground,
        fontFamilyFallback: KarmiTypography.sansFallback,
      );
  return MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
    p: bodyStyle,
    pPadding: EdgeInsets.zero,
    listBullet: bodyStyle,
    listBulletPadding: const EdgeInsets.only(right: 8),
    a: bodyStyle.copyWith(
      color: colors.primary,
      decoration: TextDecoration.underline,
    ),
    code: TextStyle(
      fontFamily: 'monospace',
      fontFamilyFallback: KarmiTypography.sansFallback,
      fontSize: (bodyStyle.fontSize ?? 16) * 0.88,
      color: colors.foreground,
    ),
    codeblockDecoration: BoxDecoration(
      color: colors.muted.withValues(alpha: 0.25),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: colors.borderSubtle),
    ),
    codeblockPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    tableBorder: TableBorder.all(color: colors.borderSubtle),
    tableBody: bodyStyle,
    tableHead: bodyStyle.copyWith(fontWeight: FontWeight.bold),
  );
}

class _ReplyActions extends StatelessWidget {
  const _ReplyActions({
    required this.reply,
    this.onFeedback,
    this.onSelectReason,
    this.onRegenerate,
  });

  final ReplyEntry reply;
  final ValueChanged<FeedbackRating>? onFeedback;
  final ValueChanged<String>? onSelectReason;
  final VoidCallback? onRegenerate;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final isBusy = reply.isFeedbackInFlight || reply.isRegenerating;
    final isDown = reply.feedbackRating == FeedbackRating.down;
    final isUp = reply.feedbackRating == FeedbackRating.up;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              iconSize: 20,
              tooltip: 'Thumbs up',
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              icon: Icon(isUp ? Icons.thumb_up : Icons.thumb_up_outlined),
              color: isUp ? colors.primaryText : colors.mutedForeground,
              isSelected: isUp,
              onPressed: isBusy || onFeedback == null
                  ? null
                  : () => onFeedback!(FeedbackRating.up),
            ),
            IconButton(
              iconSize: 20,
              tooltip: 'Thumbs down',
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              icon: Icon(isDown ? Icons.thumb_down : Icons.thumb_down_outlined),
              color: isDown ? colors.primaryText : colors.mutedForeground,
              isSelected: isDown,
              onPressed: isBusy || onFeedback == null
                  ? null
                  : () => onFeedback!(FeedbackRating.down),
            ),
            IconButton(
              iconSize: 20,
              tooltip: 'Regenerate response',
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              icon: reply.isRegenerating
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh),
              color: colors.mutedForeground,
              onPressed: isBusy || onRegenerate == null ? null : onRegenerate,
            ),
          ],
        ),
        if (isDown) ...[
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final reason in FeedbackReason.values)
                ChoiceChip(
                  label: Text(reason.label),
                  selected: reply.feedbackReason == reason.wireName,
                  onSelected: isBusy || onSelectReason == null
                      ? null
                      : (_) => onSelectReason!(reason.wireName),
                  materialTapTargetSize: MaterialTapTargetSize.padded,
                ),
            ],
          ),
        ],
      ],
    );
  }
}
