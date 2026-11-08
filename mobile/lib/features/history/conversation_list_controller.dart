import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../api/conversations/conversations_api.dart';

/// Represents a conversation pending permanent deletion, during which the user
/// may undo the deletion.
class PendingDeletion {
  const PendingDeletion(this.conversation);

  final ConversationView conversation;
}

/// Controller managing conversation list state, pagination, optimistic updates,
/// search with debouncing, and undoable deletion.
class ConversationListController extends ChangeNotifier {
  ConversationListController({
    required ConversationsApi api,
    Duration searchDebounce = const Duration(milliseconds: 250),
    Duration undoWindow = const Duration(seconds: 5),
  }) : _api = api,
       _searchDebounce = searchDebounce,
       _undoWindow = undoWindow;

  final ConversationsApi _api;
  final Duration _searchDebounce;
  final Duration _undoWindow;

  List<ConversationView> _conversations = const [];
  bool _showArchived = false;
  bool _loading = false;
  bool _loadingMore = false;
  String? _nextCursor;
  String _query = '';
  List<ConversationSearchResult> _results = const [];
  bool _searching = false;
  Object? _error;
  PendingDeletion? _pendingDeletion;

  Timer? _searchTimer;
  Timer? _undoTimer;
  int _searchSequence = 0;
  bool _disposed = false;

  /// Visible list of conversations, sorted pinned first then by updatedAt descending.
  List<ConversationView> get conversations => List.unmodifiable(_conversations);

  /// Whether currently viewing archived conversations.
  bool get showArchived => _showArchived;

  /// Whether an initial load or refresh is in progress.
  bool get loading => _loading;

  /// Whether an additional page is currently being loaded.
  bool get loadingMore => _loadingMore;

  /// Whether there are more pages available to load.
  bool get hasMore => _nextCursor != null && _nextCursor!.isNotEmpty;

  /// The current search query text.
  String get query => _query;

  /// The search results for [query].
  List<ConversationSearchResult> get results => List.unmodifiable(_results);

  /// Whether a search request is currently in flight.
  bool get searching => _searching;

  /// The last encountered error, if any.
  Object? get error => _error;

  /// The active pending deletion, if within the undo window.
  PendingDeletion? get pendingDeletion => _pendingDeletion;

  /// Refreshes the conversation list from the server for the current [showArchived] filter.
  Future<void> refresh() async {
    if (_disposed) return;
    _loading = true;
    _error = null;
    _safeNotifyListeners();

    try {
      final page = await _api.list(archived: _showArchived);
      final items = List<ConversationView>.from(page.items);
      items.sort(_compareConversations);
      _conversations = items;
      _nextCursor = page.nextCursor;
    } catch (e) {
      _error = e;
    } finally {
      _loading = false;
      _safeNotifyListeners();
    }
  }

  /// Loads the next page of conversations using [nextCursor].
  ///
  /// No-op if there are no more pages or a load is already in progress.
  Future<void> loadMore() async {
    if (!hasMore || _loading || _loadingMore || _disposed) {
      return;
    }
    _loadingMore = true;
    _error = null;
    _safeNotifyListeners();

    try {
      final page = await _api.list(
        archived: _showArchived,
        cursor: _nextCursor,
      );
      final updated = List<ConversationView>.from(_conversations);
      for (final item in page.items) {
        if (!updated.any((c) => c.id == item.id)) {
          updated.add(item);
        }
      }
      _conversations = updated;
      _nextCursor = page.nextCursor;
    } catch (e) {
      _error = e;
    } finally {
      _loadingMore = false;
      _safeNotifyListeners();
    }
  }

  /// Switches between active and archived conversations and reloads page 1.
  Future<void> setShowArchived(bool value) async {
    if (_showArchived == value) return;
    _showArchived = value;
    await refresh();
  }

  /// Updates the search query, debounces the search request, and updates results.
  ///
  /// An empty query immediately clears results and stops searching.
  void onQueryChanged(String q) {
    _query = q;
    _searchTimer?.cancel();
    final seq = ++_searchSequence;

    final trimmed = q.trim();
    if (trimmed.isEmpty) {
      _results = const [];
      _searching = false;
      _safeNotifyListeners();
      return;
    }

    _safeNotifyListeners();

    _searchTimer = Timer(_searchDebounce, () async {
      if (_disposed || seq != _searchSequence) return;
      _searching = true;
      _error = null;
      _safeNotifyListeners();

      try {
        final res = await _api.search(trimmed);
        if (_disposed || seq != _searchSequence) return;
        _results = res;
      } catch (e) {
        if (_disposed || seq != _searchSequence) return;
        _error = e;
      } finally {
        if (!_disposed && seq == _searchSequence) {
          _searching = false;
          _safeNotifyListeners();
        }
      }
    });
  }

  /// Optimistically renames conversation [id] to [title].
  ///
  /// Reverts to the snapshot and sets [error] on failure.
  Future<void> rename(String id, String title) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index == -1) return;

    final snapshot = List<ConversationView>.from(_conversations);
    final oldConv = _conversations[index];
    final updatedConv = oldConv.copyWith(title: title, titleSource: 'user');

    final next = List<ConversationView>.from(_conversations);
    next[index] = updatedConv;
    _conversations = next;
    _error = null;
    _safeNotifyListeners();

    try {
      final serverConv = await _api.update(id, title: title);
      final idx = _conversations.indexWhere((c) => c.id == id);
      if (idx != -1) {
        final list = List<ConversationView>.from(_conversations);
        list[idx] = serverConv;
        list.sort(_compareConversations);
        _conversations = list;
        _safeNotifyListeners();
      }
    } catch (e) {
      _conversations = snapshot;
      _error = e;
      _safeNotifyListeners();
    }
  }

  /// Optimistically toggles the pinned status of conversation [id].
  ///
  /// Reorders the list with pinned items first, then by updatedAt descending.
  /// Reverts to snapshot and sets [error] on failure.
  Future<void> togglePin(String id) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index == -1) return;

    final snapshot = List<ConversationView>.from(_conversations);
    final oldConv = _conversations[index];
    final newPinned = !oldConv.pinned;
    final updatedConv = oldConv.copyWith(pinned: newPinned);

    final next = List<ConversationView>.from(_conversations);
    next[index] = updatedConv;
    next.sort(_compareConversations);
    _conversations = next;
    _error = null;
    _safeNotifyListeners();

    try {
      final serverConv = await _api.update(id, pinned: newPinned);
      final idx = _conversations.indexWhere((c) => c.id == id);
      if (idx != -1) {
        final list = List<ConversationView>.from(_conversations);
        list[idx] = serverConv;
        list.sort(_compareConversations);
        _conversations = list;
        _safeNotifyListeners();
      }
    } catch (e) {
      _conversations = snapshot;
      _error = e;
      _safeNotifyListeners();
    }
  }

  /// Optimistically updates the archived state of conversation [id].
  ///
  /// Removes the conversation from the visible list if it no longer matches
  /// [showArchived]. Reverts to snapshot on failure.
  Future<void> setArchived(String id, bool archived) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index == -1) return;

    final snapshot = List<ConversationView>.from(_conversations);
    final oldConv = _conversations[index];

    if (archived != _showArchived) {
      _conversations = List<ConversationView>.from(_conversations)
        ..removeAt(index);
    } else {
      final updated = oldConv.copyWith(
        archivedAt: archived ? (oldConv.archivedAt ?? DateTime.now()) : null,
      );
      final next = List<ConversationView>.from(_conversations);
      next[index] = updated;
      next.sort(_compareConversations);
      _conversations = next;
    }
    _error = null;
    _safeNotifyListeners();

    try {
      await _api.update(id, archived: archived);
    } catch (e) {
      _conversations = snapshot;
      _error = e;
      _safeNotifyListeners();
    }
  }

  /// Optimistically removes conversation [id], establishes a [pendingDeletion],
  /// and calls the server delete endpoint.
  ///
  /// On failure, the conversation is restored and [error] is set.
  /// The undo window timer will dismiss the pending deletion after [undoWindow].
  Future<void> delete(String id) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index == -1) return;

    final snapshot = List<ConversationView>.from(_conversations);
    final conv = _conversations[index];

    _undoTimer?.cancel();
    _pendingDeletion = PendingDeletion(conv);
    _conversations = List<ConversationView>.from(_conversations)
      ..removeAt(index);
    _error = null;
    _safeNotifyListeners();

    _undoTimer = Timer(_undoWindow, () {
      dismissPendingDeletion();
    });

    try {
      await _api.delete(id);
    } catch (e) {
      _undoTimer?.cancel();
      _undoTimer = null;
      _pendingDeletion = null;
      _conversations = snapshot;
      _error = e;
      _safeNotifyListeners();
    }
  }

  /// Restores the currently pending deletion on the server and re-inserts
  /// the conversation into the list in sorted order.
  Future<void> undoDelete() async {
    final pending = _pendingDeletion;
    if (pending == null) return;

    _undoTimer?.cancel();
    _undoTimer = null;

    try {
      final restored = await _api.restore(pending.conversation.id);
      _pendingDeletion = null;
      final updated = List<ConversationView>.from(_conversations);
      if (!updated.any((c) => c.id == restored.id)) {
        updated.add(restored);
      }
      updated.sort(_compareConversations);
      _conversations = updated;
      _error = null;
      _safeNotifyListeners();
    } catch (e) {
      _error = e;
      _safeNotifyListeners();
    }
  }

  /// Dismisses the active [pendingDeletion] and cancels the undo timer.
  void dismissPendingDeletion() {
    _undoTimer?.cancel();
    _undoTimer = null;
    if (_pendingDeletion != null) {
      _pendingDeletion = null;
      _safeNotifyListeners();
    }
  }

  void _safeNotifyListeners() {
    if (!_disposed) {
      notifyListeners();
    }
  }

  static int _compareConversations(ConversationView a, ConversationView b) {
    if (a.pinned != b.pinned) {
      return a.pinned ? -1 : 1;
    }
    final cmp = b.updatedAt.compareTo(a.updatedAt);
    if (cmp != 0) return cmp;
    return b.id.compareTo(a.id);
  }

  @override
  void dispose() {
    _disposed = true;
    _searchTimer?.cancel();
    _searchTimer = null;
    _undoTimer?.cancel();
    _undoTimer = null;
    super.dispose();
  }
}
