import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../theme/karmi_motion.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../tasks/task_confirmation_sheet.dart';
import 'chat_entry.dart';
import 'composer.dart';
import 'message_bubble.dart';
import 'status_chip.dart';

/// Chat tab: empty, pending, per-outcome replies, and failed / offline /
/// in-flight (409) / limit-reached (429) states. No streaming or history exists
/// server-side, so the transcript is in memory only.
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.api, this.onOpenPlans});

  final KarmiApi api;
  final VoidCallback? onOpenPlans;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<ChatEntry> _entries = [];
  final _scroll = ScrollController();
  int _nextId = 0;
  UserEntry? _pending;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _send(String text) {
    final entry = UserEntry(
      id: 'u${_nextId++}',
      text: text,
      idempotencyKey: KarmiApi.newIdempotencyKey(),
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
      );
      if (!mounted) return;
      setState(() {
        entry.state = SendState.sent;
        _entries.add(ReplyEntry(id: 'r${_nextId++}', message: reply));
      });
    } on KarmiApiException catch (error) {
      if (!mounted) return;
      setState(() {
        entry.state = switch (error) {
          NetworkException() => SendState.offline,
          InFlightException() => SendState.inFlight,
          LimitReachedException() => SendState.limitReached,
          _ => SendState.failed,
        };
        if (error is LimitReachedException) entry.resetAt = error.resetAt;
      });
    } finally {
      if (mounted) setState(() => _pending = null);
    }
    _scrollToEnd();
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
                          'Ask for a draft, a task, or something to remember.',
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
