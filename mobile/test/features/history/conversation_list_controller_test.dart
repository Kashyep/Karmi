import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';

class FakeConversationsApi implements ConversationsApi {
  @override
  String get baseUrl => 'http://fake.local';

  @override
  Duration get timeout => const Duration(seconds: 5);

  @override
  Future<String?> Function()? tokenProvider;

  @override
  void close() {}

  Future<ConversationPage> Function({bool archived, String? cursor, int limit})?
  onList;
  Future<List<ConversationSearchResult>> Function(String q, {int limit})?
  onSearch;
  Future<ConversationView> Function(String id)? onGet;
  Future<MessagePage> Function(String id, {String? before, int limit})?
  onMessages;
  Future<ConversationView> Function(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  })?
  onUpdate;
  Future<void> Function(String id)? onDelete;
  Future<ConversationView> Function(String id)? onRestore;

  final List<String> searchCalls = [];
  final List<({String id, String? title, bool? pinned, bool? archived})>
  updateCalls = [];
  final List<String> deleteCalls = [];
  final List<String> restoreCalls = [];
  final List<({bool archived, String? cursor, int limit})> listCalls = [];
  final Map<String, ConversationView> _known = {};

  @override
  Future<ConversationPage> list({
    bool archived = false,
    String? cursor,
    int limit = 20,
  }) async {
    listCalls.add((archived: archived, cursor: cursor, limit: limit));
    if (onList != null) {
      final page = await onList!(
        archived: archived,
        cursor: cursor,
        limit: limit,
      );
      for (final item in page.items) {
        _known[item.id] = item;
      }
      return page;
    }
    return const ConversationPage(items: []);
  }

  @override
  Future<List<ConversationSearchResult>> search(
    String q, {
    int limit = 20,
  }) async {
    searchCalls.add(q);
    if (onSearch != null) {
      return onSearch!(q, limit: limit);
    }
    return const [];
  }

  @override
  Future<ConversationView> get(String id) async {
    if (onGet != null) return onGet!(id);
    throw UnimplementedError();
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    if (onMessages != null) {
      return onMessages!(id, before: before, limit: limit);
    }
    return const MessagePage(items: []);
  }

  @override
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async {
    updateCalls.add((id: id, title: title, pinned: pinned, archived: archived));
    if (onUpdate != null) {
      return onUpdate!(id, title: title, pinned: pinned, archived: archived);
    }
    final existing = _known[id];
    if (existing != null) {
      final updated = existing.copyWith(
        title: title ?? existing.title,
        pinned: pinned ?? existing.pinned,
        archivedAt: archived != null
            ? (archived ? (existing.archivedAt ?? DateTime.now()) : null)
            : existing.archivedAt,
      );
      _known[id] = updated;
      return updated;
    }
    return ConversationView(
      id: id,
      title: title,
      pinned: pinned ?? false,
      updatedAt: DateTime.now(),
    );
  }

  @override
  Future<void> delete(String id) async {
    deleteCalls.add(id);
    if (onDelete != null) {
      return onDelete!(id);
    }
  }

  @override
  Future<ConversationView> restore(String id) async {
    restoreCalls.add(id);
    if (onRestore != null) {
      return onRestore!(id);
    }
    final existing = _known[id];
    if (existing != null) {
      final restored = existing.copyWith(archivedAt: null);
      _known[id] = restored;
      return restored;
    }
    return ConversationView(id: id, updatedAt: DateTime.now());
  }
}

ConversationView makeConversation({
  required String id,
  String? title,
  bool pinned = false,
  DateTime? updatedAt,
  DateTime? archivedAt,
}) {
  return ConversationView(
    id: id,
    title: title ?? 'Conv $id',
    pinned: pinned,
    updatedAt: updatedAt ?? DateTime.utc(2026, 1, 1),
    archivedAt: archivedAt,
  );
}

void main() {
  group('search', () {
    test('debounce collapses rapid query changes into one search', () {
      fakeAsync((async) {
        final api = FakeConversationsApi();
        final controller = ConversationListController(
          api: api,
          searchDebounce: const Duration(milliseconds: 250),
        );
        addTearDown(controller.dispose);

        controller.onQueryChanged('f');
        async.elapse(const Duration(milliseconds: 50));
        controller.onQueryChanged('fo');
        async.elapse(const Duration(milliseconds: 50));
        controller.onQueryChanged('foo');

        expect(api.searchCalls, isEmpty);
        async.elapse(const Duration(milliseconds: 250));
        expect(api.searchCalls, equals(['foo']));
      });
    });

    test('stale search response ignored', () {
      fakeAsync((async) {
        final api = FakeConversationsApi();
        final completer1 = Completer<List<ConversationSearchResult>>();
        final completer2 = Completer<List<ConversationSearchResult>>();

        api.onSearch = (q, {limit = 20}) {
          if (q == 'first') return completer1.future;
          if (q == 'second') return completer2.future;
          return Future.value([]);
        };

        final controller = ConversationListController(
          api: api,
          searchDebounce: const Duration(milliseconds: 100),
        );
        addTearDown(controller.dispose);

        controller.onQueryChanged('first');
        async.elapse(const Duration(milliseconds: 100));
        expect(api.searchCalls, equals(['first']));

        // Trigger second search while first is in-flight
        controller.onQueryChanged('second');
        async.elapse(const Duration(milliseconds: 100));
        expect(api.searchCalls, equals(['first', 'second']));

        // Second response completes first
        final secondResults = [
          ConversationSearchResult(
            conversation: makeConversation(id: 'c2', title: 'Second'),
            snippet: 'Second',
            matched: 'title',
          ),
        ];
        completer2.complete(secondResults);
        async.flushMicrotasks();
        expect(controller.results, equals(secondResults));

        // Stale first response arrives later
        final firstResults = [
          ConversationSearchResult(
            conversation: makeConversation(id: 'c1', title: 'First'),
            snippet: 'First',
            matched: 'title',
          ),
        ];
        completer1.complete(firstResults);
        async.flushMicrotasks();

        // Stale response must be ignored
        expect(controller.results, equals(secondResults));
      });
    });

    test('empty query immediately clears results and stops searching', () {
      fakeAsync((async) {
        final api = FakeConversationsApi();
        final controller = ConversationListController(
          api: api,
          searchDebounce: const Duration(milliseconds: 100),
        );
        addTearDown(controller.dispose);

        controller.onQueryChanged('test');
        async.elapse(const Duration(milliseconds: 100));

        controller.onQueryChanged('');
        expect(controller.results, isEmpty);
        expect(controller.searching, isFalse);
        expect(controller.query, isEmpty);
      });
    });
  });

  group('optimistic mutations', () {
    test('optimistic rename reverted on failure', () async {
      final initial = makeConversation(id: 'c1', title: 'Original');
      final completer = Completer<ConversationView>();
      final api = FakeConversationsApi();
      api.onList = ({archived = false, cursor, limit = 20}) async =>
          ConversationPage(items: [initial]);
      api.onUpdate = (id, {title, pinned, archived}) => completer.future;

      final controller = ConversationListController(api: api);
      addTearDown(controller.dispose);
      await controller.refresh();
      expect(controller.conversations.first.title, 'Original');

      final future = controller.rename('c1', 'Renamed');
      // Optimistic update
      expect(controller.conversations.first.title, 'Renamed');

      completer.completeError(Exception('Update failed'));
      await future;

      // Reverted
      expect(controller.conversations.first.title, 'Original');
      expect(controller.error, isNotNull);
    });

    test('togglePin reorders', () async {
      final conv1 = makeConversation(
        id: 'c1',
        pinned: false,
        updatedAt: DateTime.utc(2026, 1, 2),
      );
      final conv2 = makeConversation(
        id: 'c2',
        pinned: false,
        updatedAt: DateTime.utc(2026, 1, 1),
      );
      final api = FakeConversationsApi()
        ..onList = ({archived = false, cursor, limit = 20}) async =>
            ConversationPage(items: [conv1, conv2]);

      final controller = ConversationListController(api: api);
      addTearDown(controller.dispose);
      await controller.refresh();
      expect(controller.conversations.map((c) => c.id).toList(), ['c1', 'c2']);

      // Pin c2 (older updatedAt, but now pinned)
      await controller.togglePin('c2');
      expect(controller.conversations.map((c) => c.id).toList(), ['c2', 'c1']);
      expect(controller.conversations.first.pinned, isTrue);

      // Unpin c2
      await controller.togglePin('c2');
      expect(controller.conversations.map((c) => c.id).toList(), ['c1', 'c2']);
      expect(controller.conversations.first.pinned, isFalse);
    });

    test(
      'setArchived removes item from current list when filter mismatches',
      () async {
        final conv = makeConversation(id: 'c1');
        final api = FakeConversationsApi()
          ..onList = ({archived = false, cursor, limit = 20}) async =>
              ConversationPage(items: [conv]);

        final controller = ConversationListController(api: api);
        addTearDown(controller.dispose);
        await controller.refresh();
        expect(controller.conversations.length, 1);

        await controller.setArchived('c1', true);
        expect(controller.conversations, isEmpty);
        expect(api.updateCalls.last.archived, isTrue);
      },
    );
  });

  group('deletion and undo', () {
    test('delete then undo restores', () async {
      final conv1 = makeConversation(
        id: 'c1',
        updatedAt: DateTime.utc(2026, 1, 2),
      );
      final conv2 = makeConversation(
        id: 'c2',
        updatedAt: DateTime.utc(2026, 1, 1),
      );
      final api = FakeConversationsApi();
      api.onList = ({archived = false, cursor, limit = 20}) async =>
          ConversationPage(items: [conv1, conv2]);
      api.onRestore = (id) async => conv1;

      final controller = ConversationListController(api: api);
      addTearDown(controller.dispose);
      await controller.refresh();

      await controller.delete('c1');
      expect(controller.conversations.map((c) => c.id).toList(), ['c2']);
      expect(controller.pendingDeletion?.conversation.id, 'c1');
      expect(api.deleteCalls, equals(['c1']));

      await controller.undoDelete();
      expect(controller.conversations.map((c) => c.id).toList(), ['c1', 'c2']);
      expect(controller.pendingDeletion, isNull);
      expect(api.restoreCalls, equals(['c1']));
    });

    test('undo window expiry clears pendingDeletion', () {
      fakeAsync((async) {
        final conv = makeConversation(id: 'c1');
        final api = FakeConversationsApi()
          ..onList = ({archived = false, cursor, limit = 20}) async =>
              ConversationPage(items: [conv]);

        final controller = ConversationListController(
          api: api,
          undoWindow: const Duration(seconds: 5),
        );
        addTearDown(controller.dispose);

        controller.refresh();
        async.flushMicrotasks();

        controller.delete('c1');
        async.flushMicrotasks();

        expect(controller.pendingDeletion, isNotNull);

        async.elapse(const Duration(seconds: 4));
        expect(controller.pendingDeletion, isNotNull);

        async.elapse(const Duration(seconds: 1));
        expect(controller.pendingDeletion, isNull);
      });
    });

    test(
      'delete failure restores conversation and clears pendingDeletion',
      () async {
        final conv = makeConversation(id: 'c1');
        final api = FakeConversationsApi();
        api.onList = ({archived = false, cursor, limit = 20}) async =>
            ConversationPage(items: [conv]);
        api.onDelete = (id) async => throw Exception('Delete error');

        final controller = ConversationListController(api: api);
        addTearDown(controller.dispose);
        await controller.refresh();

        await controller.delete('c1');
        expect(controller.conversations.map((c) => c.id).toList(), ['c1']);
        expect(controller.pendingDeletion, isNull);
        expect(controller.error, isNotNull);
      },
    );
  });

  group('pagination and filters', () {
    test('setShowArchived reloads', () async {
      final active = makeConversation(id: 'act1');
      final archivedConv = makeConversation(
        id: 'arch1',
        archivedAt: DateTime.utc(2026, 1, 1),
      );

      final api = FakeConversationsApi()
        ..onList = ({archived = false, cursor, limit = 20}) async {
          if (archived) {
            return ConversationPage(items: [archivedConv]);
          } else {
            return ConversationPage(items: [active]);
          }
        };

      final controller = ConversationListController(api: api);
      addTearDown(controller.dispose);

      await controller.refresh();
      expect(controller.showArchived, isFalse);
      expect(controller.conversations.map((c) => c.id).toList(), ['act1']);

      await controller.setShowArchived(true);
      expect(controller.showArchived, isTrue);
      expect(controller.conversations.map((c) => c.id).toList(), ['arch1']);
      expect(api.listCalls.last.archived, isTrue);
    });

    test('loadMore appends', () async {
      final conv1 = makeConversation(
        id: 'c1',
        updatedAt: DateTime.utc(2026, 1, 3),
      );
      final conv2 = makeConversation(
        id: 'c2',
        updatedAt: DateTime.utc(2026, 1, 2),
      );
      final conv3 = makeConversation(
        id: 'c3',
        updatedAt: DateTime.utc(2026, 1, 1),
      );

      final api = FakeConversationsApi()
        ..onList = ({archived = false, cursor, limit = 20}) async {
          if (cursor == null) {
            return ConversationPage(
              items: [conv1, conv2],
              nextCursor: 'cur_page_2',
            );
          } else if (cursor == 'cur_page_2') {
            return ConversationPage(items: [conv3], nextCursor: null);
          }
          return const ConversationPage(items: []);
        };

      final controller = ConversationListController(api: api);
      addTearDown(controller.dispose);

      await controller.refresh();
      expect(controller.conversations.map((c) => c.id).toList(), ['c1', 'c2']);
      expect(controller.hasMore, isTrue);

      await controller.loadMore();
      expect(controller.conversations.map((c) => c.id).toList(), [
        'c1',
        'c2',
        'c3',
      ]);
      expect(controller.hasMore, isFalse);
    });
  });

  group('lifecycle', () {
    test('dispose cancels timers', () {
      fakeAsync((async) {
        final api = FakeConversationsApi();
        final controller = ConversationListController(
          api: api,
          searchDebounce: const Duration(milliseconds: 250),
          undoWindow: const Duration(seconds: 5),
        );

        controller.onQueryChanged('pending');
        controller.dispose();

        async.elapse(const Duration(milliseconds: 300));
        expect(api.searchCalls, isEmpty);
      });
    });
  });
}
