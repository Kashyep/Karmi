import 'package:flutter/material.dart';

import '../../widgets/karmi_card.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';
import 'bug_report_detail_screen.dart';
import 'paged_admin_list.dart';

/// Admin inbox for user-submitted bug reports.
class BugInboxScreen extends StatefulWidget {
  const BugInboxScreen({super.key, required this.controller});

  final AdminController controller;

  @override
  State<BugInboxScreen> createState() => _BugInboxScreenState();
}

class _BugInboxScreenState extends State<BugInboxScreen> {
  String _status = 'all';
  String _category = 'all';

  late final PagedAdminList<AdminBugReportItem> _list =
      PagedAdminList<AdminBugReportItem>(
        controller: widget.controller,
        fetch: (api, token, cursor) async {
          final page = await api.listBugReports(
            token,
            status: _status == 'all' ? null : _status,
            category: _category == 'all' ? null : _category,
            cursor: cursor,
          );
          return (items: page.items, nextCursor: page.nextCursor);
        },
      );

  @override
  void initState() {
    super.initState();
    _list.reload();
  }

  @override
  void dispose() {
    _list.dispose();
    super.dispose();
  }

  Future<void> _openDetail(String id) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            BugReportDetailScreen(controller: widget.controller, reportId: id),
      ),
    );
    if (changed == true && mounted) {
      _list.reload();
    }
  }

  Widget _filters() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FilterChip(
                  label: const Text('All statuses'),
                  selected: _status == 'all',
                  onSelected: (_) {
                    if (_status != 'all') {
                      setState(() => _status = 'all');
                      _list.reload();
                    }
                  },
                ),
              ),
              for (final s in kAllowedBugReportStatuses)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    label: Text(bugReportStatusLabel(s)),
                    selected: _status == s,
                    onSelected: (_) {
                      setState(() => _status = s);
                      _list.reload();
                    },
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FilterChip(
                  label: const Text('All categories'),
                  selected: _category == 'all',
                  onSelected: (_) {
                    if (_category != 'all') {
                      setState(() => _category = 'all');
                      _list.reload();
                    }
                  },
                ),
              ),
              for (final c in kBugReportCategories)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    label: Text(bugReportCategoryLabel(c)),
                    selected: _category == c,
                    onSelected: (_) {
                      setState(() => _category = c);
                      _list.reload();
                    },
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _list,
      builder: (context, _) {
        final items = _list.items;
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: items.length + 2, // filters + items + footer
          itemBuilder: (context, index) {
            if (index == 0) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _filters(),
              );
            }
            if (index == items.length + 1) {
              return PagedListFooter<AdminBugReportItem>(
                list: _list,
                loadingLabel: 'Loading bug reports',
                loadMoreLabel: 'Load more reports',
                emptyText: 'No bug reports match the filters.',
                failureTitle: "Couldn't load bug reports",
              );
            }
            final report = items[index - 1];
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _BugReportRow(
                report: report,
                onTap: () => _openDetail(report.id),
              ),
            );
          },
        );
      },
    );
  }
}

class _BugReportRow extends StatelessWidget {
  const _BugReportRow({required this.report, required this.onTap});

  final AdminBugReportItem report;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final statusText = bugReportStatusLabel(report.status);
    final userLabel =
        report.userDisplayName != null && report.userDisplayName!.isNotEmpty
        ? report.userDisplayName!
        : (report.userId ?? 'Unknown user');
    final dateStr = formatAdminDateTime(context, report.createdAt);

    return KarmiCard(
      padding: EdgeInsets.zero,
      child: ListTile(
        minTileHeight: 48,
        onTap: onTap,
        title: Row(
          children: [
            Text(report.ticket, style: text.titleMedium),
            const SizedBox(width: 8),
            Text(
              '· ${bugReportCategoryLabel(report.category)}',
              style: text.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.outline,
              ),
            ),
          ],
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 4),
            Text(
              report.descriptionPreview,
              style: text.bodyMedium,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 4),
            Text(
              '$userLabel · $dateStr',
              style: text.labelMedium?.copyWith(
                color: Theme.of(context).colorScheme.outline,
              ),
            ),
          ],
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (report.hasScreenshot) ...[
              const Icon(Icons.image_outlined, size: 18),
              const SizedBox(width: 8),
            ],
            Text(
              statusText,
              style: text.labelLarge?.copyWith(fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}
