import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../widgets/feedback.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';

typedef AdminPageFetch<T> =
    Future<({List<T> items, String? nextCursor})> Function(
      AdminApi api,
      String token,
      String? cursor,
    );

/// Cursor-paged list shared by Users and Audit. [reload] replaces the items
/// and [loadMore] appends the next page. A reload that starts while another
/// request is in flight wins: responses from the older request are dropped.
class PagedAdminList<T> extends ChangeNotifier {
  PagedAdminList({
    required this.controller,
    required this.fetch,
    this.order,
  });

  final AdminController controller;
  final AdminPageFetch<T> fetch;

  /// Applied after every page is appended, so newest entries stay on top.
  final Comparator<T>? order;

  final List<T> _items = [];
  String? _nextCursor;
  bool _loading = false;
  Object? _error;
  int _generation = 0;
  bool _disposed = false;

  List<T> get items => List.unmodifiable(_items);
  bool get loading => _loading;
  bool get hasMore => _nextCursor != null;
  Object? get error => _error;

  Future<void> reload() => _run(reset: true);

  Future<void> loadMore() {
    if (!hasMore || _loading) return Future.value();
    return _run(reset: false);
  }

  Future<void> _run({required bool reset}) async {
    final generation = ++_generation;
    final cursor = reset ? null : _nextCursor;
    if (reset) {
      _items.clear();
      _nextCursor = null;
    }
    _loading = true;
    _error = null;
    notifyListeners();

    ({List<T> items, String? nextCursor})? page;
    Object? failure;
    try {
      page = await runAdminCall(
        controller,
        (api, token) => fetch(api, token, cursor),
      );
    } on AdminException catch (e) {
      failure = e;
    }
    if (_disposed || generation != _generation) return;
    _loading = false;
    if (page != null) {
      _items.addAll(page.items);
      if (order != null) _items.sort(order);
      _nextCursor = page.nextCursor;
    } else {
      _error = failure;
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

/// List footer: loader while a page is in flight, retry on failure, "Load
/// more" when the server reported another page, and [emptyText] when no
/// items match.
class PagedListFooter<T> extends StatelessWidget {
  const PagedListFooter({
    super.key,
    required this.list,
    required this.loadingLabel,
    required this.loadMoreLabel,
    required this.emptyText,
    required this.failureTitle,
  });

  final PagedAdminList<T> list;
  final String loadingLabel;
  final String loadMoreLabel;
  final String emptyText;
  final String failureTitle;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    final error = list.error;
    if (list.loading) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: KarmiLoader(label: loadingLabel),
      );
    }
    if (error != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: ErrorBanner(
          icon: Icons.cloud_off,
          tone: ErrorTone.warning,
          title: failureTitle,
          message: adminErrorMessage(error),
          actionLabel: 'Retry',
          onAction: list.items.isEmpty ? list.reload : list.loadMore,
        ),
      );
    }
    if (list.items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Text(
          emptyText,
          textAlign: TextAlign.center,
          style: text.bodyLarge?.copyWith(color: colors.mutedForeground),
        ),
      );
    }
    if (list.hasMore) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: OutlinedButton(
          style: kAdminButtonStyle,
          onPressed: list.loadMore,
          child: Text(loadMoreLabel),
        ),
      );
    }
    return const SizedBox(height: 8);
  }
}
