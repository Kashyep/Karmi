import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../api/chat/chat_models.dart';
import '../../api/models.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';
import '../../widgets/karmi_card.dart';
import 'chat_entry.dart';
import 'rendering/markdown_message.dart';
import 'status_chip.dart';

/// A chat bubble on an opaque surface, capped to a readable line length.
class MessageBubble extends StatelessWidget {
  const MessageBubble.user({super.key, required UserEntry this.entry})
    : reply = null,
      chatMessage = null,
      announce = false,
      onReviewDetails = null,
      onFeedback = null,
      onSelectReason = null,
      onRegenerate = null,
      onContinue = null,
      onResume = null;

  const MessageBubble.reply({
    super.key,
    required ReplyEntry this.reply,
    this.announce = false,
    this.onReviewDetails,
    this.onFeedback,
    this.onSelectReason,
    this.onRegenerate,
  })  : entry = null,
        chatMessage = null,
        onContinue = null,
        onResume = null;

  const MessageBubble.chatMessage({
    super.key,
    required ChatMessageView this.chatMessage,
    this.announce = false,
    this.onReviewDetails,
    this.onFeedback,
    this.onSelectReason,
    this.onRegenerate,
    this.onContinue,
    this.onResume,
  })  : entry = null,
        reply = null;

  final UserEntry? entry;
  final ReplyEntry? reply;
  final ChatMessageView? chatMessage;

  /// Latest reply: exposed as a live region so screen readers announce it.
  final bool announce;

  /// Shown for `ASK_USER` replies; opens the task confirmation sheet.
  final VoidCallback? onReviewDetails;

  final ValueChanged<FeedbackRating>? onFeedback;
  final ValueChanged<String>? onSelectReason;
  final VoidCallback? onRegenerate;
  final VoidCallback? onContinue;
  final VoidCallback? onResume;
  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    final isUser = entry != null || (chatMessage != null && chatMessage!.role == 'user');

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
              ? SelectableText(
                  entry != null ? entry!.text : (chatMessage?.content ?? ''),
                  style: text.bodyLarge?.copyWith(
                    color: colors.primaryForeground,
                  ),
                )
              : chatMessage != null
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    MarkdownMessage(
                      text: chatMessage!.content,
                      streaming: chatMessage!.status == MessageStatus.streaming,
                      allowCollapse: true,
                    ),
                    if (chatMessage!.status != MessageStatus.streaming) ...[
                      const SizedBox(height: 4),
                      _ChatMessageActions(
                        message: chatMessage!,
                        onContinue: onContinue,
                        onResume: onResume,
                        onRegenerate: onRegenerate,
                      ),
                    ],
                  ],
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

class _ChatMessageActions extends StatelessWidget {
  const _ChatMessageActions({
    required this.message,
    this.onContinue,
    this.onResume,
    this.onRegenerate,
  });

  final ChatMessageView message;
  final VoidCallback? onContinue;
  final VoidCallback? onResume;
  final VoidCallback? onRegenerate;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final showContinue =
        message.finishReason == FinishReason.length && onContinue != null;
    final showResume = (message.finishReason == FinishReason.interrupted ||
            message.status == MessageStatus.interrupted) &&
        onResume != null;

    if (!showContinue && !showResume && onRegenerate == null) {
      return const SizedBox.shrink();
    }

    return Wrap(
      spacing: 8,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (showContinue)
          TextButton.icon(
            onPressed: onContinue,
            icon: const Icon(Icons.arrow_forward, size: 16),
            label: const Text('Continue'),
          ),
        if (showResume)
          TextButton.icon(
            onPressed: onResume,
            icon: const Icon(Icons.play_arrow, size: 16),
            label: const Text('Resume'),
          ),
        if (onRegenerate != null)
          IconButton(
            iconSize: 20,
            tooltip: 'Regenerate response',
            constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
            icon: const Icon(Icons.refresh),
            color: colors.mutedForeground,
            onPressed: onRegenerate,
          ),
      ],
    );
  }
}
