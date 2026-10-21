import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/chat/chat_models.dart';
import '../../api/models.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';
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
      onResume = null,
      feedbackRating = null,
      feedbackReason = null,
      isFeedbackInFlight = false;

  const MessageBubble.reply({
    super.key,
    required ReplyEntry this.reply,
    this.announce = false,
    this.onReviewDetails,
    this.onFeedback,
    this.onSelectReason,
    this.onRegenerate,
  }) : entry = null,
       chatMessage = null,
       onContinue = null,
       onResume = null,
       feedbackRating = null,
       feedbackReason = null,
       isFeedbackInFlight = false;

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
    this.feedbackRating,
    this.feedbackReason,
    this.isFeedbackInFlight = false,
  }) : entry = null,
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
  final FeedbackRating? feedbackRating;
  final String? feedbackReason;
  final bool isFeedbackInFlight;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    final isUser =
        entry != null || (chatMessage != null && chatMessage!.role == 'user');

    return LayoutBuilder(
      builder: (context, constraints) {
        if (isUser) {
          final maxWidth = constraints.maxWidth * 0.75;
          final userPill = Container(
            constraints: BoxConstraints(minHeight: 48, maxWidth: maxWidth),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: colors.userBubble,
              borderRadius: KarmiShape.userPillRadius,
            ),
            child: SelectableText(
              entry != null ? entry!.text : (chatMessage?.content ?? ''),
              style: text.bodyLarge?.copyWith(
                color: colors.foreground,
              ),
            ),
          );

          return Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Semantics(
                container: true,
                liveRegion: announce,
                label: 'You said',
                child: userPill,
              ),
            ),
          );
        }

        final assistantTurn = Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: KarmiShape.readableColumnMaxWidth,
            ),
            child: SizedBox(
              width: double.infinity,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const _KarmiAvatar(),
                      const SizedBox(width: 8),
                      Text(
                        'Karmi',
                        style: KarmiTypography.messageHeaderName().copyWith(
                          color: colors.foreground,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (reply != null) ...[
                    if (StatusChip.hasVisibleOutcome(reply!.message.outcome) &&
                        reply!.message.outcome != Outcome.askUser) ...[
                      StatusChip.outcome(reply!.message.outcome),
                      const SizedBox(height: 8),
                    ],
                    Text(
                      reply!.message.response,
                      style: text.bodyLarge?.copyWith(color: colors.foreground),
                    ),
                    if (reply!.message.outcome == Outcome.askUser) ...[
                      const SizedBox(height: 8),
                      _ConfirmationCard(onReviewDetails: onReviewDetails),
                    ],
                    const SizedBox(height: 4),
                    _ReplyActions(
                      reply: reply!,
                      onFeedback: onFeedback,
                      onSelectReason: onSelectReason,
                      onRegenerate: onRegenerate,
                    ),
                  ] else if (chatMessage != null) ...[
                    if (StatusChip.hasVisibleOutcome(chatMessage!.outcome) &&
                        chatMessage!.outcome != Outcome.askUser) ...[
                      StatusChip.outcome(chatMessage!.outcome!),
                      const SizedBox(height: 8),
                    ],
                    MarkdownMessage(
                      text: chatMessage!.content,
                      streaming: chatMessage!.status == MessageStatus.streaming,
                      allowCollapse: true,
                    ),
                    if (chatMessage!.outcome == Outcome.askUser) ...[
                      const SizedBox(height: 8),
                      _ConfirmationCard(onReviewDetails: onReviewDetails),
                    ],
                    if (chatMessage!.status != MessageStatus.streaming) ...[
                      const SizedBox(height: 4),
                      _ChatMessageActions(
                        message: chatMessage!,
                        onContinue: onContinue,
                        onResume: onResume,
                        onRegenerate: onRegenerate,
                        onFeedback: onFeedback,
                        onSelectReason: onSelectReason,
                        feedbackRating: feedbackRating,
                        feedbackReason: feedbackReason,
                        isFeedbackInFlight: isFeedbackInFlight,
                      ),
                    ],
                  ],
                ],
              ),
            ),
          ),
        );

        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Semantics(
            container: true,
            liveRegion: announce,
            label: 'Karmi replied',
            child: assistantTurn,
          ),
        );
      },
    );
  }
}

class _KarmiAvatar extends StatelessWidget {
  const _KarmiAvatar();

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    return Semantics(
      excludeSemantics: true,
      child: Container(
        width: 24,
        height: 24,
        decoration: BoxDecoration(
          color: colors.primary,
          shape: BoxShape.circle,
        ),
        alignment: Alignment.center,
        child: Text(
          'K',
          style: TextStyle(
            color: colors.primaryForeground,
            fontSize: 13,
            fontWeight: FontWeight.w700,
            height: 1,
          ),
        ),
      ),
    );
  }
}

class _ConfirmationCard extends StatelessWidget {
  const _ConfirmationCard({this.onReviewDetails});

  final VoidCallback? onReviewDetails;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: colors.warningSurface,
        borderRadius: BorderRadius.circular(KarmiShape.cardRadius),
        border: Border.all(color: colors.hairline),
      ),
      child: Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          StatusChip.outcome(Outcome.askUser),
          if (onReviewDetails != null)
            TextButton.icon(
              onPressed: onReviewDetails,
              icon: const Icon(Icons.fact_check_outlined),
              label: const Text('Review details'),
            ),
        ],
      ),
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
    return _ActionToolbar(
      copyText: reply.message.response,
      onFeedback: onFeedback,
      onSelectReason: onSelectReason,
      onRegenerate: onRegenerate,
      feedbackRating: reply.feedbackRating,
      feedbackReason: reply.feedbackReason,
      isFeedbackInFlight: reply.isFeedbackInFlight,
      isRegenerating: reply.isRegenerating,
    );
  }
}

class _ChatMessageActions extends StatelessWidget {
  const _ChatMessageActions({
    required this.message,
    this.onContinue,
    this.onResume,
    this.onRegenerate,
    this.onFeedback,
    this.onSelectReason,
    this.feedbackRating,
    this.feedbackReason,
    this.isFeedbackInFlight = false,
  });

  final ChatMessageView message;
  final VoidCallback? onContinue;
  final VoidCallback? onResume;
  final VoidCallback? onRegenerate;
  final ValueChanged<FeedbackRating>? onFeedback;
  final ValueChanged<String>? onSelectReason;
  final FeedbackRating? feedbackRating;
  final String? feedbackReason;
  final bool isFeedbackInFlight;

  @override
  Widget build(BuildContext context) {
    final showContinue =
        message.finishReason == FinishReason.length && onContinue != null;
    final showResume =
        (message.finishReason == FinishReason.interrupted ||
            message.status == MessageStatus.interrupted) &&
        onResume != null;

    Widget? extraActions;
    if (showContinue || showResume) {
      extraActions = Wrap(
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
        ],
      );
    }

    return _ActionToolbar(
      copyText: message.content,
      onFeedback: onFeedback,
      onSelectReason: onSelectReason,
      onRegenerate: onRegenerate,
      feedbackRating: feedbackRating,
      feedbackReason: feedbackReason,
      isFeedbackInFlight: isFeedbackInFlight,
      isRegenerating: false,
      extraActions: extraActions,
    );
  }
}

class _ActionToolbar extends StatefulWidget {
  const _ActionToolbar({
    required this.copyText,
    this.onFeedback,
    this.onSelectReason,
    this.onRegenerate,
    this.feedbackRating,
    this.feedbackReason,
    this.isFeedbackInFlight = false,
    this.isRegenerating = false,
    this.extraActions,
  });

  final String copyText;
  final ValueChanged<FeedbackRating>? onFeedback;
  final ValueChanged<String>? onSelectReason;
  final VoidCallback? onRegenerate;
  final FeedbackRating? feedbackRating;
  final String? feedbackReason;
  final bool isFeedbackInFlight;
  final bool isRegenerating;
  final Widget? extraActions;

  @override
  State<_ActionToolbar> createState() => _ActionToolbarState();
}

class _ActionToolbarState extends State<_ActionToolbar> {
  bool _copied = false;
  Timer? _copyTimer;

  @override
  void dispose() {
    _copyTimer?.cancel();
    super.dispose();
  }

  void _handleCopy() {
    Clipboard.setData(ClipboardData(text: widget.copyText));
    _copyTimer?.cancel();
    setState(() {
      _copied = true;
    });
    _copyTimer = Timer(const Duration(milliseconds: 1500), () {
      if (mounted) {
        setState(() {
          _copied = false;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final isBusy = widget.isFeedbackInFlight || widget.isRegenerating;
    final isDown = widget.feedbackRating == FeedbackRating.down;
    final isUp = widget.feedbackRating == FeedbackRating.up;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.extraActions != null) ...[
          widget.extraActions!,
          const SizedBox(height: 4),
        ],
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Semantics(
              label: _copied ? 'Copied' : 'Copy response',
              button: true,
              child: IconButton(
                iconSize: 20,
                tooltip: _copied ? 'Copied' : 'Copy',
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                icon: Icon(_copied ? Icons.check : Icons.copy_outlined),
                color: _copied ? colors.primaryText : colors.actionIcon,
                onPressed: _handleCopy,
              ),
            ),
            Semantics(
              label: 'Regenerate response',
              button: true,
              child: IconButton(
                iconSize: 20,
                tooltip: 'Regenerate response',
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                icon: widget.isRegenerating
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh),
                color: colors.actionIcon,
                onPressed: isBusy || widget.onRegenerate == null
                    ? null
                    : widget.onRegenerate,
              ),
            ),
            Semantics(
              label: 'Thumbs up',
              button: true,
              child: IconButton(
                iconSize: 20,
                tooltip: 'Thumbs up',
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                icon: Icon(isUp ? Icons.thumb_up : Icons.thumb_up_outlined),
                color: isUp ? colors.primaryText : colors.actionIcon,
                isSelected: isUp,
                onPressed: isBusy || widget.onFeedback == null
                    ? null
                    : () => widget.onFeedback!(FeedbackRating.up),
              ),
            ),
            Semantics(
              label: 'Thumbs down',
              button: true,
              child: IconButton(
                iconSize: 20,
                tooltip: 'Thumbs down',
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                icon: Icon(isDown ? Icons.thumb_down : Icons.thumb_down_outlined),
                color: isDown ? colors.primaryText : colors.actionIcon,
                isSelected: isDown,
                onPressed: isBusy || widget.onFeedback == null
                    ? null
                    : () => widget.onFeedback!(FeedbackRating.down),
              ),
            ),
            if (_copied) ...[
              const SizedBox(width: 4),
              Text(
                'Copied',
                style: KarmiTypography.toolbarCaption().copyWith(
                  color: colors.actionIcon,
                ),
              ),
            ],
          ],
        ),
        if (isDown) ...[
          const SizedBox(height: 4),
          Text(
            'Reason for rating',
            style: KarmiTypography.toolbarCaption().copyWith(
              color: colors.mutedForeground,
            ),
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final reason in FeedbackReason.values)
                ChoiceChip(
                  label: Text(reason.label),
                  selected: widget.feedbackReason == reason.wireName,
                  onSelected: isBusy || widget.onSelectReason == null
                      ? null
                      : (_) => widget.onSelectReason!(reason.wireName),
                  materialTapTargetSize: MaterialTapTargetSize.padded,
                ),
            ],
          ),
        ],
      ],
    );
  }
}
