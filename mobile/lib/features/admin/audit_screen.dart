import 'package:flutter/material.dart';

import '../../widgets/karmi_card.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';
import 'paged_admin_list.dart';

/// Newest entries first; entries without a timestamp sort last.
int _newestFirst(AuditEntry a, AuditEntry b) {
  final ax = a.at;
  final bx = b.at;
  if (ax == null && bx == null) return 0;
  if (ax == null) return 1;
  if (bx == null) return -1;
  return bx.compareTo(ax);
}

/// Audit log of admin actions, newest first, paged with Load more.
class AuditScreen extends StatefulWidget {
  const AuditScreen({super.key, required this.controller});

  final AdminController controller;

  @override
  State<AuditScreen> createState() => _AuditScreenState();
}

class _AuditScreenState extends State<AuditScreen> {
  late final PagedAdminList<AuditEntry> _list = PagedAdminList(
    controller: widget.controller,
    order: _newestFirst,
    fetch: (api, token, cursor) async {
      final page = await api.audit(token, cursor: cursor);
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

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _list,
      builder: (context, _) {
        final items = _list.items;
        return ListView.builder(
          padding: kAdminPagePadding,
          itemCount: items.length + 1,
          itemBuilder: (context, index) {
            if (index == items.length) {
              return PagedListFooter<AuditEntry>(
                list: _list,
                loadingLabel: 'Loading audit entries',
                loadMoreLabel: 'Load more entries',
                emptyText: 'No audit entries yet.',
                failureTitle: "Couldn't load the audit log",
              );
            }
            return _AuditRow(entry: items[index]);
          },
        );
      },
    );
  }
}

class _AuditRow extends StatelessWidget {
  const _AuditRow({required this.entry});

  final AuditEntry entry;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final time = formatAdminDateTime(context, entry.at);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Semantics(
        container: true,
        child: KarmiCard(
          semanticContainer: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(entry.action, style: text.titleMedium),
              const SizedBox(height: 4),
              _line(context, 'Target', entry.targetUserId),
              _line(context, 'Reason', entry.reason),
              _line(context, 'Admin', entry.adminUserId),
              Text(time, style: text.bodySmall),
            ],
          ),
        ),
      ),
    );
  }

  Widget _line(BuildContext context, String label, String? value) {
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Text(
        '$label: ${value == null || value.isEmpty ? kAdminUnavailable : value}',
        style: text.bodyMedium,
      ),
    );
  }
}
