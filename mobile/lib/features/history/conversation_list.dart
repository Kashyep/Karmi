import 'package:flutter/material.dart';

import '../../api/chat/chat_models.dart';
import '../../theme/karmi_colors.dart';
import 'conversation_actions.dart';
import 'conversation_groups.dart';
import 'conversation_list_controller.dart';
import 'search_field.dart';

sealed class _HistoryEntry {
  const _HistoryEntry();
}

class _GroupHeaderEntry extends _HistoryEntry {
  const _GroupHeaderEntry(this.title, {required this.isFirst});
  final String title;
  final bool isFirst;
}

class _ConversationEntry extends _HistoryEntry {
  const _ConversationEntry(this.conversation);
  final ConversationView conversation;
}

class _LoadingMoreEntry extends _HistoryEntry {
  const _LoadingMoreEntry();
}

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
    this.activeConversationId,
    this.clock,
  });

  final ValueChanged<String> onOpen;
  final VoidCallback onNewChat;
  final ConversationListController controller;
  final String? activeConversationId;

  /// Injectable clock for relative dates and date grouping; null uses the wall clock.
  final DateTime Function()? clock;

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
    final karmiColors = Theme.of(context).extension<KarmiColors>();
    final sidebarSurface =
        karmiColors?.sidebarSurface ?? theme.colorScheme.surface;
    final hairline = karmiColors?.hairline ?? theme.dividerColor;

    return ListenableBuilder(
      listenable: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final isSearching = controller.query.trim().isNotEmpty;

        return Material(
          color: sidebarSurface,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: SearchField(
                  key: const ValueKey('conversation-search-field'),
                  onChanged: controller.onQueryChanged,
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                child: Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilledButton.icon(
                      key: const ValueKey('new-chat-button'),
                      icon: const Icon(Icons.add),
                      label: const Text('New chat'),
                      onPressed: widget.onNewChat,
                    ),
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
              Divider(height: 1, thickness: 1, color: hairline),
              if (controller.error != null)
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color:
                          karmiColors?.errorSurface ??
                          theme.colorScheme.errorContainer,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color:
                            karmiColors?.destructive.withValues(alpha: 0.3) ??
                            theme.colorScheme.error.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          Icons.error_outline,
                          size: 16,
                          color:
                              karmiColors?.destructive ??
                              theme.colorScheme.error,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            '${controller.error}',
                            style: TextStyle(
                              color:
                                  karmiColors?.foreground ??
                                  theme.colorScheme.onErrorContainer,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              Expanded(
                child: isSearching
                    ? _buildSearchResults(
                        context,
                        controller,
                        hairline,
                        karmiColors,
                      )
                    : _buildConversationList(
                        context,
                        controller,
                        hairline,
                        karmiColors,
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSearchResults(
    BuildContext context,
    ConversationListController controller,
    Color hairline,
    KarmiColors? karmiColors,
  ) {
    final theme = Theme.of(context);

    if (controller.searching && controller.results.isEmpty) {
      return Center(
        child: SizedBox.square(
          dimension: 24,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: karmiColors?.primary,
          ),
        ),
      );
    }

    if (controller.results.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.search_off,
                size: 40,
                color: karmiColors?.mutedForeground ?? theme.disabledColor,
              ),
              const SizedBox(height: 12),
              Text(
                'No conversations match "${controller.query}"',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: karmiColors?.mutedForeground,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      );
    }

    return ListView.separated(
      controller: _scrollController,
      itemCount: controller.results.length,
      separatorBuilder: (_, __) =>
          Divider(height: 1, thickness: 1, color: hairline),
      itemBuilder: (context, index) {
        final result = controller.results[index];
        final conv = result.conversation;
        final isActive = widget.activeConversationId == conv.id;
        final title = conv.title?.trim().isNotEmpty == true
            ? conv.title!
            : 'Untitled chat';

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          child: Material(
            color: isActive
                ? (karmiColors?.card ?? theme.colorScheme.surfaceContainerHigh)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            child: Container(
              decoration: isActive
                  ? BoxDecoration(
                      borderRadius: BorderRadius.circular(8),
                      border: Border(
                        top: BorderSide(
                          color:
                              karmiColors?.glassSpecularRim ??
                              theme.colorScheme.outlineVariant.withValues(
                                alpha: 0.25,
                              ),
                          width: 1,
                        ),
                      ),
                    )
                  : null,
              child: ListTile(
                dense: true,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                title: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: isActive
                      ? const TextStyle(fontWeight: FontWeight.w500)
                      : null,
                ),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (result.snippet.isNotEmpty)
                      Text(
                        result.snippet,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: karmiColors?.mutedForeground,
                        ),
                      ),
                    const SizedBox(height: 2),
                    Text(
                      'Matched in ${result.matched}',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color:
                            karmiColors?.primary ?? theme.colorScheme.primary,
                      ),
                    ),
                  ],
                ),
                trailing: IconButton(
                  icon: const Icon(Icons.more_vert),
                  tooltip: 'Actions',
                  constraints: const BoxConstraints(
                    minWidth: 44,
                    minHeight: 44,
                  ),
                  onPressed: () => showConversationActions(
                    context,
                    conversation: conv,
                    controller: controller,
                  ),
                ),
                onTap: () => widget.onOpen(conv.id),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildConversationList(
    BuildContext context,
    ConversationListController controller,
    Color hairline,
    KarmiColors? karmiColors,
  ) {
    final theme = Theme.of(context);

    if (controller.loading && controller.conversations.isEmpty) {
      return Center(
        child: SizedBox.square(
          dimension: 24,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: karmiColors?.primary,
          ),
        ),
      );
    }

    if (controller.conversations.isEmpty) {
      return RefreshIndicator(
        onRefresh: controller.refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            SizedBox(height: MediaQuery.sizeOf(context).height * 0.15),
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      controller.showArchived
                          ? Icons.archive_outlined
                          : Icons.chat_bubble_outline,
                      size: 40,
                      color:
                          karmiColors?.mutedForeground ?? theme.disabledColor,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      controller.showArchived
                          ? 'No archived conversations'
                          : 'No conversations yet',
                      style: theme.textTheme.bodyLarge?.copyWith(
                        color: karmiColors?.mutedForeground,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
    }

    final now = (widget.clock ?? DateTime.now)();
    final groups = groupConversationsByDate(controller.conversations, now);
    final entries = <_HistoryEntry>[];
    for (var i = 0; i < groups.length; i++) {
      final group = groups[i];
      entries.add(_GroupHeaderEntry(group.title, isFirst: i == 0));
      for (final conv in group.conversations) {
        entries.add(_ConversationEntry(conv));
      }
    }
    if (controller.loadingMore) {
      entries.add(const _LoadingMoreEntry());
    }

    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView.builder(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount: entries.length,
        itemBuilder: (context, index) {
          final entry = entries[index];
          switch (entry) {
            case _GroupHeaderEntry(:final title, :final isFirst):
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (!isFirst)
                    Divider(height: 16, thickness: 1, color: hairline),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                    child: Text(
                      title,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color:
                            karmiColors?.mutedForeground ??
                            theme.colorScheme.onSurfaceVariant,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ],
              );

            case _LoadingMoreEntry():
              return const Padding(
                padding: EdgeInsets.all(16),
                child: Center(
                  child: SizedBox.square(
                    dimension: 24,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                ),
              );

            case _ConversationEntry(:final conversation):
              final conv = conversation;
              final isActive = widget.activeConversationId == conv.id;
              final title = conv.title?.trim().isNotEmpty == true
                  ? conv.title!
                  : 'Untitled chat';
              final relativeDate = formatRelativeDate(conv.updatedAt, now);

              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                child: Material(
                  color: isActive
                      ? (karmiColors?.card ??
                            theme.colorScheme.surfaceContainerHigh)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    decoration: isActive
                        ? BoxDecoration(
                            borderRadius: BorderRadius.circular(8),
                            border: Border(
                              top: BorderSide(
                                color:
                                    karmiColors?.glassSpecularRim ??
                                    theme.colorScheme.outlineVariant.withValues(
                                      alpha: 0.25,
                                    ),
                                width: 1,
                              ),
                            ),
                          )
                        : null,
                    child: ListTile(
                      dense: true,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      leading: conv.pinned
                          ? Icon(
                              Icons.push_pin,
                              size: 20,
                              color:
                                  karmiColors?.primary ??
                                  theme.colorScheme.primary,
                            )
                          : null,
                      title: Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: isActive
                            ? const TextStyle(fontWeight: FontWeight.w500)
                            : null,
                      ),
                      subtitle: Text(
                        relativeDate,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: karmiColors?.mutedForeground,
                        ),
                      ),
                      trailing: IconButton(
                        icon: const Icon(Icons.more_vert),
                        tooltip: 'Actions',
                        constraints: const BoxConstraints(
                          minWidth: 44,
                          minHeight: 44,
                        ),
                        onPressed: () => showConversationActions(
                          context,
                          conversation: conv,
                          controller: controller,
                        ),
                      ),
                      onTap: () => widget.onOpen(conv.id),
                    ),
                  ),
                ),
              );
          }
        },
      ),
    );
  }
}
