import 'package:flutter/material.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../api/karmi_api.dart';

class StatusChip extends StatelessWidget {
  final Outcome outcome;
  final String text;

  const StatusChip({super.key, required this.outcome, required this.text});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>()!;

    Color chipColor;
    IconData icon;

    switch (outcome) {
      case Outcome.ACCEPT:
        chipColor = colors.primary; // Or success token
        icon = Icons.check_circle_outline;
        break;
      case Outcome.REPAIR:
        chipColor = colors.accent;
        icon = Icons.build_circle_outlined;
        break;
      case Outcome.ESCALATE:
      case Outcome.ASK_USER:
      case Outcome.SAFE_STOP:
        chipColor = colors.secondary; // Or warning token
        icon = Icons.error_outline;
        break;
      case Outcome.DEFERRED:
      default:
        chipColor = colors.mutedForeground;
        icon = Icons.schedule;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: chipColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: chipColor.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: chipColor),
          const SizedBox(width: 4),
          Text(
            text,
            style: Theme.of(context)
                .textTheme
                .labelSmall
                ?.copyWith(color: chipColor),
          ),
        ],
      ),
    );
  }
}

class MessageBubble extends StatelessWidget {
  final String text;
  final bool isUser;
  final Outcome? outcome;

  const MessageBubble({
    super.key,
    required this.text,
    required this.isUser,
    this.outcome,
  });

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>()!;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        padding: const EdgeInsets.all(12),
        constraints:
            BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
        decoration: BoxDecoration(
          color: isUser ? colors.primary : colors.card,
          borderRadius: BorderRadius.circular(14),
          border: isUser ? null : Border.all(color: colors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (outcome != null) ...[
              StatusChip(outcome: outcome!, text: outcome!.name),
              const SizedBox(height: 8),
            ],
            Text(
              text,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: isUser
                        ? colors.primaryForeground
                        : colors.cardForeground,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class Composer extends StatefulWidget {
  final ValueChanged<String> onSend;
  final bool isPending;

  const Composer({super.key, required this.onSend, this.isPending = false});

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  final _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>()!;

    return KarmiGlassContainer(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: colors.card,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: colors.border),
                ),
                child: TextField(
                  controller: _controller,
                  decoration: const InputDecoration(
                    hintText: 'Type a message...',
                    border: InputBorder.none,
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  ),
                  onSubmitted: (val) {
                    if (val.isNotEmpty && !widget.isPending) {
                      widget.onSend(val);
                      _controller.clear();
                    }
                  },
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              icon: widget.isPending
                  ? const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : Icon(Icons.send, color: colors.primary),
              onPressed: widget.isPending
                  ? null
                  : () {
                      final text = _controller.text;
                      if (text.isNotEmpty) {
                        widget.onSend(text);
                        _controller.clear();
                      }
                    },
            ),
          ],
        ),
      ),
    );
  }
}

class ChatScreen extends StatefulWidget {
  final KarmiApi api;

  const ChatScreen({super.key, required this.api});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<MessageView> _messages = [];
  bool _isPending = false;

  Future<void> _sendMessage(String text) async {
    setState(() {
      _messages.add(MessageView(
          runId: 'temp',
          status: 'sending',
          outcome: Outcome.ACCEPT, // Unused for user bubble
          response: text,
          route: 'user'));
      _isPending = true;
    });

    try {
      final response = await widget.api.sendMessage(text);
      setState(() {
        _messages.add(response);
        _isPending = false;
      });
    } catch (e) {
      setState(() {
        _isPending = false;
        // Basic error handling for Phase 3
        _messages.add(MessageView(
            runId: 'error',
            status: 'error',
            outcome: Outcome.SAFE_STOP,
            response: 'Could not complete request: $e',
            route: 'error'));
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(vertical: 16),
            itemCount: _messages.length,
            itemBuilder: (context, index) {
              final msg = _messages[index];
              final isUser = msg.route == 'user';
              return MessageBubble(
                text: msg.response,
                isUser: isUser,
                outcome: isUser ? null : msg.outcome,
              );
            },
          ),
        ),
        Composer(
          onSend: _sendMessage,
          isPending: _isPending,
        ),
      ],
    );
  }
}
