import 'package:flutter/material.dart';

import 'conversation_actions.dart';
import 'conversation_list_controller.dart';
import 'search_field.dart';

/// Formats [at] relative to [now] (e.g. 'Just now', '5m ago', '2h ago', '3d ago', '2026-10-21').
String formatRelativeDate(DateTime at, [DateTime? now]) {
  final current = (now ?? DateTime.now()).toUtc();
  final target = at.toUtc();
  final diff = current.difference(target);

  if (diff.isNegative || diff.inSeconds < 60) {
    return 'Just now';
  } else if (diff.inMinutes < 60) {
    return '${diff.inMinutes}m ago';
  } else if (diff.inHours < 24) {
    return '${diff.inHours}h ago';
  } else if (diff.inDays < 7) {
    return '${diff.inDays}d ago';
  } else {
    final m = target.month.toString().padLeft(2, '0');
    final d = target.day.toString().padLeft(2, '0');
    return '${target.year}-$m-$d';
  }
}

/// A screen widget displaying the conversation history list, search results,
/// archived toggle, and new chat action.
class ConversationList extends StatefulWidget {
  const ConversationList({
    super.key,
    required this.onOpen,
    required this.onNewChat,
    required this.controller,
  });

  final ValueChanged<String> onOpen;
  final VoidCallback onNewChat;
  final ConversationListController controller;

  @override
  State<ConversationList> createState() => _ConversationListState();
}

class _ConversationListState extends State<ConversationList> {
  final ScrollController _scrollController = ScrollController();
  PendingDeletion? _lastPendingDeletion;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    widget.controller.addListener(_onControllerChanged);
    _lastPendingDeletion = widget.controller.pendingDeletion;
    if (_lastPendingDeletion != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _showUndoSnackBar();
      });
    }
  }

  @override
  void didUpdateWidget(ConversationList oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.controller != oldWidget.controller) {
      oldWidget.controller.removeListener(_onControllerChanged);
      widget.controller.addListener(_onControllerChanged);
      _lastPendingDeletion = widget.controller.pendingDeletion;
      if (_lastPendingDeletion != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _showUndoSnackBar();
        });
      }
    }
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    widget.controller.removeListener(_onControllerChanged);
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.maxScrollExtent - position.pixels <= 200) {
      if (widget.controller.hasMore && !widget.controller.loadingMore) {
        widget.controller.loadMore();
      }
    }
  }

  void _onControllerChanged() {
    final current = widget.controller.pendingDeletion;
    if (current != null && current != _lastPendingDeletion) {
      _lastPendingDeletion = current;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _showUndoSnackBar();
      });
    } else if (current == null) {
      _lastPendingDeletion = null;
    }
  }

  void _showUndoSnackBar() {
    if (!mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (messenger == null) return;

    messenger.hideCurrentSnackBar();
    final controller = messenger.showSnackBar(
      SnackBar(
        content: const Text('Chat deleted'),
        duration: const Duration(seconds: 5),
        action: SnackBarAction(
          label: 'Undo',
          onPressed: () {
            widget.controller.undoDelete();
          },
        ),
      ),
    );

    controller.closed.then((_) {
      if (mounted) {
        widget.controller.dismissPendingDeletion();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListenableBuilder(
      listenable: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final isSearching = controller.query.trim().isNotEmpty;

        return Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: SearchField(
                key: const ValueKey('conversation-search-field'),
                onChanged: controller.onQueryChanged,
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: Row(
                children: [
                  FilledButton.icon(
                    key: const ValueKey('new-chat-button'),
                    icon: const Icon(Icons.add),
                    label: const Text('New chat'),
                    onPressed: widget.onNewChat,
                  ),
                  const Spacer(),
                  FilterChip(
                    key: const ValueKey('archived-filter-chip'),
                    label: const Text('Archived'),
                    selected: controller.showArchived,
                    onSelected: (selected) {
                      controller.setShowArchived(selected);
                    },
                  ),
                ],
              ),
            ),
            if (controller.error != null)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                child: Text(
                  '${controller.error}',
                  style: TextStyle(color: theme.colorScheme.error),
                  textAlign: TextAlign.center,
                ),
              ),
            Expanded(
              child: isSearching
                  ? _buildSearchResults(context, controller)
                  : _buildConversationList(context, controller),
            ),
          ],
        );
      },
    );
  }

  Widget _buildSearchResults(
    BuildContext context,
    ConversationListController controller,
  ) {
    final theme = Theme.of(context);

    if (controller.searching && controller.results.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (controller.results.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'No conversations match "${controller.query}"',
            style: theme.textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    return ListView.separated(
      controller: _scrollController,
      itemCount: controller.results.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final result = controller.results[index];
        final conv = result.conversation;
        final title = conv.title?.trim().isNotEmpty == true
            ? conv.title!
            : 'Untitled chat';

        return ListTile(
          title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (result.snippet.isNotEmpty)
                Text(
                  result.snippet,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium,
                ),
              const SizedBox(height: 2),
              Text(
                'Matched in ${result.matched}',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.primary,
                ),
              ),
            ],
          ),
          trailing: IconButton(
            icon: const Icon(Icons.more_vert),
            tooltip: 'Actions',
            onPressed: () => showConversationActions(
              context,
              conversation: conv,
              controller: controller,
            ),
          ),
          onTap: () => widget.onOpen(conv.id),
        );
      },
    );
  }

  Widget _buildConversationList(
    BuildContext context,
    ConversationListController controller,
  ) {
    final theme = Theme.of(context);

    if (controller.loading && controller.conversations.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (controller.conversations.isEmpty) {
      return RefreshIndicator(
        onRefresh: controller.refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            SizedBox(height: MediaQuery.sizeOf(context).height * 0.2),
            Center(
              child: Text(
                controller.showArchived
                    ? 'No archived conversations'
                    : 'No conversations yet',
                style: theme.textTheme.bodyLarge,
              ),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView.separated(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount:
            controller.conversations.length + (controller.loadingMore ? 1 : 0),
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          if (index == controller.conversations.length) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(
                child: SizedBox.square(
                  dimension: 24,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            );
          }

          final conv = controller.conversations[index];
          final title = conv.title?.trim().isNotEmpty == true
              ? conv.title!
              : 'Untitled chat';
          final relativeDate = formatRelativeDate(conv.updatedAt);

          return ListTile(
            leading: conv.pinned
                ? Icon(
                    Icons.push_pin,
                    size: 20,
                    color: theme.colorScheme.primary,
                  )
                : null,
            title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(relativeDate, style: theme.textTheme.bodySmall),
            trailing: IconButton(
              icon: const Icon(Icons.more_vert),
              tooltip: 'Actions',
              onPressed: () => showConversationActions(
                context,
                conversation: conv,
                controller: controller,
              ),
            ),
            onTap: () => widget.onOpen(conv.id),
          );
        },
      ),
    );
  }
}
