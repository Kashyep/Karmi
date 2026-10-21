import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';

/// Integrated chat header row (§3.1, §5.7).
///
/// Houses history toggle, active conversation title (or 'New chat'),
/// optional plans link, and quick 'New chat' action button.
class KarmiChatHeader extends StatelessWidget {
  const KarmiChatHeader({
    super.key,
    required this.title,
    this.onOpenHistory,
    required this.onNewChat,
    this.onOpenPlans,
    this.trailing,
  });

  final String title;
  final VoidCallback? onOpenHistory;
  final VoidCallback onNewChat;
  final VoidCallback? onOpenPlans;
  final Widget? trailing;

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
              IconButton(
                key: const ValueKey('chat-header-history'),
                icon: const Icon(Icons.history),
                tooltip: 'Conversation history',
                color: colors.actionIcon,
                constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                padding: const EdgeInsets.all(10),
                onPressed: onOpenHistory,
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
            const SizedBox(width: 8),
            if (onOpenPlans != null) ...[
              TextButton(
                style: TextButton.styleFrom(
                  minimumSize: const Size(44, 44),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  foregroundColor: colors.primaryText,
                ),
                onPressed: onOpenPlans,
                child: const Text('Plans'),
              ),
              const SizedBox(width: 4),
            ],
            IconButton(
              key: const ValueKey('chat-header-new-chat'),
              icon: const Icon(Icons.add),
              tooltip: 'New chat',
              color: colors.actionIcon,
              constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
              padding: const EdgeInsets.all(10),
              onPressed: onNewChat,
            ),
            if (trailing != null) trailing!,
          ],
        ),
      ),
    );
  }
}
