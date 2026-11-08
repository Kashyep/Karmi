import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';

/// Houses history toggle, active conversation title (or 'New chat'),
/// and quick 'New chat' action button.
class KarmiChatHeader extends StatelessWidget {
  const KarmiChatHeader({
    super.key,
    required this.title,
    this.onOpenHistory,
    this.onNewChat,
  });

  final String title;
  final VoidCallback? onOpenHistory;
  final VoidCallback? onNewChat;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final theme = Theme.of(context);
    final displayTitle = title.trim().isEmpty ? 'New chat' : title;

    return SafeArea(
      bottom: false,
      child: Container(
        constraints: const BoxConstraints(minHeight: 48),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Row(
          children: [
            if (onOpenHistory != null) ...[
              Semantics(
                button: true,
                label: 'Conversation history',
                child: IconButton(
                  key: const ValueKey('chat-header-history'),
                  icon: const Icon(Icons.history),
                  tooltip: 'Conversation history',
                  color: colors.actionIcon,
                  constraints: const BoxConstraints(
                    minWidth: 44,
                    minHeight: 44,
                  ),
                  padding: const EdgeInsets.all(10),
                  onPressed: onOpenHistory,
                ),
              ),
              const SizedBox(width: 8),
            ],
            Expanded(
              child: Semantics(
                header: true,
                child: Text(
                  displayTitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: colors.foreground,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            Semantics(
              button: true,
              enabled: onNewChat != null,
              label: 'New chat',
              child: IconButton(
                key: const ValueKey('chat-header-new-chat'),
                icon: const Icon(Icons.add),
                tooltip: 'New chat',
                color: colors.actionIcon,
                constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                padding: const EdgeInsets.all(10),
                onPressed: onNewChat,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
