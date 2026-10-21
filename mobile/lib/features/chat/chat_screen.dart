import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../theme/karmi_motion.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../tasks/task_confirmation_sheet.dart';
import 'chat_controller.dart';
import 'chat_entry.dart';

export 'chat_controller.dart';
import 'composer.dart';
import 'message_bubble.dart';
import 'status_chip.dart';

/// Chat tab: empty, pending, per-outcome replies, and failed / offline /
/// in-flight (409) / limit-reached (429) states. No streaming or history exists
/// server-side, so the transcript is in memory only.
class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.api,
    this.controller,
    this.onOpenPlans,
  });

  final KarmiApi api;
  final ChatController? controller;
  final VoidCallback? onOpenPlans;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<ChatEntry> _entries = [];
  final _scroll = ScrollController();
  int _nextId = 0;
  UserEntry? _pending;
  _ActionError? _actionError;

  @override
  void initState() {
    super.initState();
    widget.controller?.addListener(_newChat);
  }

  @override
  void didUpdateWidget(covariant ChatScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?.removeListener(_newChat);
      widget.controller?.addListener(_newChat);
    }
  }

  @override
  void dispose() {
    widget.controller?.removeListener(_newChat);
    _scroll.dispose();
    super.dispose();
  }

  void _newChat() {
    setState(() {
      _entries.clear();
      _pending = null;
      _actionError = null;
    });
  }

  void _send(String text) {
    _actionError = null;
    final history = buildHistoryFromEntries(_entries);
    final entry = UserEntry(
      id: 'u${_nextId++}',
      text: text,
      idempotencyKey: KarmiApi.newIdempotencyKey(),
      history: history,
    );
    setState(() => _entries.add(entry));
    _deliver(entry);
  }

  /// Retries reuse the entry's idempotency key.
  void _retry(UserEntry entry) {
    setState(() => entry.state = SendState.sending);
    _deliver(entry);
  }

  Future<void> _deliver(UserEntry entry) async {
    setState(() => _pending = entry);
    _scrollToEnd();
    try {
      final reply = await widget.api.sendMessage(
        entry.text,
        idempotencyKey: entry.idempotencyKey,
        history: entry.history,
      );
      if (!mounted) return;
      if (!_entries.contains(entry)) return;
      setState(() {
        entry.state = SendState.sent;
        _entries.add(ReplyEntry(id: 'r${_nextId++}', message: reply));
      });
    } on KarmiApiException catch (error) {
      if (!mounted) return;
      if (!_entries.contains(entry)) return;
      setState(() {
        entry.state = switch (error) {
          NetworkException() => SendState.offline,
          InFlightException() => SendState.inFlight,
          LimitReachedException() => SendState.limitReached,
          BetaCapacityFullException() => SendState.capacityFull,
          _ => SendState.failed,
        };
        if (error is LimitReachedException) entry.resetAt = error.resetAt;
        if (error is BetaCapacityFullException) entry.resetAt = error.resetAt;
      });
    } finally {
      // A New chat may have started another send meanwhile; only clear our own.
      if (mounted && identical(_pending, entry)) {
        setState(() => _pending = null);
      }
    }
    _scrollToEnd();
  }

  void _updateReply(ReplyEntry oldEntry, ReplyEntry newEntry) {
    final index = _entries.indexOf(oldEntry);
    if (index != -1) {
      _entries[index] = newEntry;
    }
  }

  Future<void> _onFeedback(ReplyEntry reply, FeedbackRating rating) async {
    final updated = reply.copyWith(
      feedbackRating: rating,
      clearReason: rating == FeedbackRating.up,
      isFeedbackInFlight: true,
    );
    setState(() {
      _updateReply(reply, updated);
      _actionError = null;
    });
    try {
      await widget.api.sendFeedback(
        reply.message.runId,
        rating: rating,
        reason: updated.feedbackReason,
      );
    } on KarmiApiException catch (error) {
      // The reply is gone after New chat: no banner for a cleared transcript.
      if (!mounted || !_entries.contains(updated)) return;
      setState(() {
        _actionError = _ActionError(
          title: "Couldn't send feedback",
          message: error is NetworkException
              ? "Karmi couldn't reach the server. Check your connection and retry."
              : 'Something went wrong on the server while sending feedback.',
          retry: () => _onFeedback(updated, rating),
        );
      });
    } finally {
      if (mounted) {
        setState(
          () => _updateReply(
            updated,
            updated.copyWith(isFeedbackInFlight: false),
          ),
        );
      }
    }
  }

  Future<void> _onSelectReason(ReplyEntry reply, String reason) async {
    final updated = reply.copyWith(
      feedbackReason: reason,
      isFeedbackInFlight: true,
    );
    setState(() {
      _updateReply(reply, updated);
      _actionError = null;
    });
    try {
      await widget.api.sendFeedback(
        reply.message.runId,
        rating: updated.feedbackRating ?? FeedbackRating.down,
        reason: reason,
      );
    } on KarmiApiException catch (error) {
      if (!mounted || !_entries.contains(updated)) return;
      setState(() {
        _actionError = _ActionError(
          title: "Couldn't send feedback",
          message: error is NetworkException
              ? "Karmi couldn't reach the server. Check your connection and retry."
              : 'Something went wrong on the server while sending feedback.',
          retry: () => _onSelectReason(updated, reason),
        );
      });
    } finally {
      if (mounted) {
        setState(
          () => _updateReply(
            updated,
            updated.copyWith(isFeedbackInFlight: false),
          ),
        );
      }
    }
  }

  Future<void> _onRegenerate(ReplyEntry reply) async {
    final replyIndex = _entries.indexWhere((e) => e.id == reply.id);
    final prompt = replyIndex <= 0
        ? null
        : _entries.take(replyIndex).whereType<UserEntry>().lastOrNull;
    if (prompt == null) return;
    final updated = reply.copyWith(isRegenerating: true);
    setState(() {
      _updateReply(reply, updated);
      _actionError = null;
    });
    try {
      final newReply = await widget.api.regenerateRun(
        reply.message.runId,
        text: prompt.text,
        idempotencyKey: KarmiApi.newIdempotencyKey(),
        reason: reply.feedbackReason,
        history: prompt.history,
      );
      if (!mounted) return;
      setState(() {
        final replacement = ReplyEntry(id: 'r${_nextId++}', message: newReply);
        _updateReply(updated, replacement);
      });
    } on KarmiApiException catch (error) {
      if (!mounted || !_entries.contains(updated)) return;
      setState(() {
        _actionError = _ActionError(
          title: "Couldn't regenerate reply",
          message: error is NetworkException
              ? "Karmi couldn't reach the server. Check your connection and retry."
              : 'Something went wrong on the server while regenerating the reply.',
          retry: () => _onRegenerate(updated),
        );
      });
    } finally {
      if (mounted) {
        setState(
          () => _updateReply(updated, updated.copyWith(isRegenerating: false)),
        );
      }
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final target = _scroll.position.maxScrollExtent;
      final duration = KarmiMotion.duration(context);
      if (duration == Duration.zero) {
        _scroll.jumpTo(target);
      } else {
        _scroll.animateTo(target, duration: duration, curve: Curves.easeOut);
      }
    });
  }

  UserEntry? get _failed {
    for (final entry in _entries.reversed) {
      if (entry is UserEntry) {
        return entry.state == SendState.sent || entry.state == SendState.sending
            ? null
            : entry;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final insets = karmiPageInsets(context);
    final lastReply = _entries.lastIndexWhere((e) => e is ReplyEntry);
    final failed = _failed;

    return Column(
      children: [
        Expanded(
          child: _entries.isEmpty
              ? ListView(
                  padding: insets.copyWith(bottom: 16),
                  children: const [
                    EmptyState(
                      quote:
                          'Ask a study question, or get help with maths or code.',
                      body:
                          'Each reply shows its status, such as "Completed" or '
                          '"Awaiting confirmation".',
                    ),
                  ],
                )
              : ListView.builder(
                  controller: _scroll,
                  padding: insets.copyWith(bottom: 16),
                  itemCount: _entries.length,
                  itemBuilder: (context, index) => switch (_entries[index]) {
                    final UserEntry e => _UserRow(entry: e),
                    final ReplyEntry r => MessageBubble.reply(
                      key: ValueKey(r.id),
                      reply: r,
                      announce: index == lastReply,
                      onReviewDetails: () =>
                          showTaskConfirmationSheet(context, r.message),
                      onFeedback: (rating) => _onFeedback(r, rating),
                      onSelectReason: (reason) => _onSelectReason(r, reason),
                      onRegenerate: () => _onRegenerate(r),
                    ),
                  },
                ),
        ),
        AnimatedSwitcher(
          duration: KarmiMotion.duration(context, KarmiMotion.fast),
          child: _pending != null
              ? const Padding(
                  key: ValueKey('chat-pending'),
                  padding: EdgeInsets.fromLTRB(20, 4, 20, 4),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: KarmiLoader(label: 'Working on your message'),
                  ),
                )
              : failed != null
              ? Padding(
                  key: ValueKey('chat-banner-${failed.id}-${failed.state}'),
                  padding: const EdgeInsets.fromLTRB(12, 4, 12, 0),
                  child: _banner(failed),
                )
              : _actionError != null
              ? Padding(
                  key: const ValueKey('chat-action-error'),
                  padding: const EdgeInsets.fromLTRB(12, 4, 12, 0),
                  child: ErrorBanner(
                    title: _actionError!.title,
                    message: _actionError!.message,
                    actionLabel: 'Retry',
                    onAction: _actionError!.retry,
                  ),
                )
              : const SizedBox.shrink(key: ValueKey('chat-idle')),
        ),
        Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.paddingOf(context).bottom,
          ),
          child: Composer(onSend: _send, isPending: _pending != null),
        ),
      ],
    );
  }

  Widget _banner(UserEntry entry) {
    void retry() => _retry(entry);
    return switch (entry.state) {
      SendState.offline => ErrorBanner(
        icon: Icons.cloud_off,
        tone: ErrorTone.warning,
        title: "You're offline",
        message:
            "Karmi couldn't reach the server. Your message is kept here; "
            'retry when you are connected.',
        actionLabel: 'Retry',
        onAction: retry,
      ),
      SendState.inFlight => ErrorBanner(
        icon: Icons.hourglass_top,
        tone: ErrorTone.info,
        title: 'Still working on this message',
        message:
            'The server is still processing it. Retry to see the result; '
            'you will not be charged twice.',
        actionLabel: 'Check again',
        onAction: retry,
      ),
      SendState.limitReached => ErrorBanner(
        icon: Icons.data_usage,
        tone: ErrorTone.warning,
        title: 'Allowance reached',
        message: entry.resetAt == null
            ? 'Your everyday allowance is used up. You can continue after it '
                  'resets, or view plans.'
            : 'Your everyday allowance resets at '
                  '${_formatReset(context, entry.resetAt!)}. You can continue '
                  'then, or view plans.',
        actionLabel: widget.onOpenPlans == null ? null : 'View plans',
        onAction: widget.onOpenPlans,
      ),
      SendState.capacityFull => ErrorBanner(
        icon: Icons.groups,
        tone: ErrorTone.warning,
        title: 'Karmi beta is full for today',
        message: entry.resetAt == null
            ? "The beta has used today's free AI replies. Your message is "
                  'kept here; try again tomorrow.'
            : "The beta has used today's free AI replies. Your message is "
                  'kept here; try again after '
                  '${_formatReset(context, entry.resetAt!)}.',
        actionLabel: 'Retry',
        onAction: retry,
      ),
      _ => ErrorBanner(
        title: 'Could not complete',
        message:
            'Something went wrong on the server. Your message is kept here.',
        actionLabel: 'Retry',
        onAction: retry,
      ),
    };
  }
}

class _ActionError {
  const _ActionError({required this.title, required this.message, this.retry});

  final String title;
  final String message;
  final VoidCallback? retry;
}

String _formatReset(BuildContext context, DateTime resetAt) {
  final local = resetAt.toLocal();
  final time = TimeOfDay.fromDateTime(local).format(context);
  final now = DateTime.now();
  final sameDay =
      local.year == now.year &&
      local.month == now.month &&
      local.day == now.day;
  return sameDay
      ? time
      : '$time on ${MaterialLocalizations.of(context).formatMediumDate(local)}';
}

class _UserRow extends StatelessWidget {
  const _UserRow({required this.entry});

  final UserEntry entry;

  @override
  Widget build(BuildContext context) {
    final chip = switch (entry.state) {
      SendState.sending || SendState.sent => null,
      SendState.inFlight => const StatusChip(
        label: 'Still working',
        icon: Icons.hourglass_top,
        tone: StatusTone.info,
      ),
      SendState.limitReached => const StatusChip(
        label: 'Allowance reached',
        icon: Icons.data_usage,
        tone: StatusTone.warning,
      ),
      SendState.capacityFull => const StatusChip(
        label: 'Beta full today',
        icon: Icons.groups,
        tone: StatusTone.warning,
      ),
      SendState.offline => const StatusChip(
        label: 'Not sent: offline',
        icon: Icons.cloud_off,
        tone: StatusTone.warning,
      ),
      SendState.failed => const StatusChip(
        label: 'Could not complete',
        icon: Icons.error_outline,
        tone: StatusTone.danger,
      ),
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        MessageBubble.user(key: ValueKey(entry.id), entry: entry),
        if (chip != null)
          Padding(padding: const EdgeInsets.only(bottom: 6), child: chip),
      ],
    );
  }
}

/// Extracts recent turns from [entries] for context:
/// - Completed UserEntry + ReplyEntry pairs BEFORE the message being sent.
/// - Skips pairs whose user entry failed/offline/limit/capacity or reply outcome is DEFERRED.
/// - Content truncated/skipped to fit 1..8000 chars (skip empty; truncate >8000 chars).
/// - Newest 20 turns max (i.e. keep the last 20 turn objects, oldest first in the list).
List<HistoryTurn> buildHistoryFromEntries(List<ChatEntry> entries) {
  final turns = <HistoryTurn>[];
  for (var i = 0; i < entries.length - 1; i++) {
    final user = entries[i];
    final reply = entries[i + 1];
    if (user is UserEntry && reply is ReplyEntry) {
      if (user.state != SendState.sent) continue;
      if (reply.message.outcome == Outcome.deferred) continue;

      final uText = user.text;
      if (uText.isNotEmpty) {
        turns.add(
          HistoryTurn(role: 'user', content: truncateHistoryContent(uText)),
        );
      }

      final rText = reply.message.response;
      if (rText.isNotEmpty) {
        turns.add(
          HistoryTurn(
            role: 'assistant',
            content: truncateHistoryContent(rText),
          ),
        );
      }
    }
  }
  if (turns.length > 20) {
    return turns.sublist(turns.length - 20);
  }
  return turns;
}

/// Truncates [text] to at most 8000 UTF-16 code units safely.
/// If the code unit at index 7999 is a high surrogate (0xD800-0xDBFF),
/// it cuts at 7999 instead to avoid splitting a surrogate pair.
String truncateHistoryContent(String text) {
  if (text.length <= 8000) return text;
  final cu = text.codeUnitAt(7999);
  if (cu >= 0xD800 && cu <= 0xDBFF) {
    return text.substring(0, 7999);
  }
  return text.substring(0, 8000);
}
