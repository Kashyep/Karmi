import 'dart:async';

import 'package:flutter/material.dart';

import '../../widgets/focus_ring.dart';
import '../../widgets/karmi_card.dart';
import 'admin_action_dialog.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';
import 'paged_admin_list.dart';
import 'user_detail_screen.dart';

const Duration kAdminSearchDebounce = Duration(milliseconds: 400);

/// Users section: debounced search, tier and status filters, and a paged
/// list. Tapping a row opens [UserDetailScreen].
class UsersScreen extends StatefulWidget {
  const UsersScreen({super.key, required this.controller});

  final AdminController controller;

  @override
  State<UsersScreen> createState() => _UsersScreenState();
}

class _UsersScreenState extends State<UsersScreen> {
  final _search = TextEditingController();
  String _tier = 'all';
  String _status = 'all';
  String _testerLabel = '';
  bool _expiringSoon = false;
  Timer? _debounce;
  final Set<String> _selected = {};
  late final PagedAdminList<AdminUser> _list = PagedAdminList(
    controller: widget.controller,
    fetch: (api, token, cursor) async {
      final q = _search.text.trim();
      final page = await api.listUsers(
        token,
        q: q.isEmpty ? null : q,
        tier: _tier == 'all' ? null : _tier,
        status: _status == 'all' ? null : _status,
        testerLabel: _testerLabel.trim().isEmpty ? null : _testerLabel.trim(),
        planExpiringBefore: _expiringSoon
            ? DateTime.now().add(const Duration(days: 30))
            : null,
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
    _debounce?.cancel();
    _list.dispose();
    _search.dispose();
    super.dispose();
  }

  void _scheduleReload() {
    _debounce?.cancel();
    _debounce = Timer(kAdminSearchDebounce, _list.reload);
  }

  Future<void> _open(AdminUser user) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            UserDetailScreen(controller: widget.controller, userId: user.id),
      ),
    );
    if (changed == true) _list.reload();
  }

  Future<void> _bulkSetPlan() async {
    if (_selected.isEmpty) return;
    final input = await showAdminActionDialog(
      context,
      title: 'Set plan for ${_selected.length} users',
      confirmLabel: 'Set plan',
      fields: [
        AdminDialogField(
          name: 'tier',
          label: 'Plan',
          initial: kAdminTiers.first,
          options: [
            for (final tier in kAdminTiers)
              AdminDialogOption(tier, adminTierLabel(tier)),
          ],
        ),
        const AdminDialogField(
          name: 'expires_at',
          label: 'Expiry (ISO date, optional)',
        ),
      ],
    );
    if (input == null || !mounted) return;
    try {
      await runAdminCall(
        widget.controller,
        (api, token) => api.bulkTier(
          token,
          _selected.toList(),
          tier: input['tier']!,
          reason: input.reason,
          expiresAt: DateTime.tryParse(input['expires_at'] ?? ''),
        ),
      );
      if (mounted) {
        setState(() => _selected.clear());
        _list.reload();
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Plans updated.')));
      }
    } on AdminException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(adminErrorMessage(error))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _list,
      builder: (context, _) {
        final items = _list.items;
        return ListView.builder(
          padding: kAdminPagePadding,
          // 0 = filters, then one row per user, then the footer.
          itemCount: items.length + 2,
          itemBuilder: (context, index) {
            if (index == 0) return _filters();
            if (index == items.length + 1) {
              return PagedListFooter<AdminUser>(
                list: _list,
                loadingLabel: 'Loading users',
                loadMoreLabel: 'Load more users',
                emptyText: 'No users match these filters.',
                failureTitle: "Couldn't load users",
              );
            }
            return _UserRow(
              user: items[index - 1],
              selected: _selected.contains(items[index - 1].id),
              onTap: () => _open(items[index - 1]),
              onLongPress: () => setState(() {
                final id = items[index - 1].id;
                if (!_selected.add(id)) _selected.remove(id);
              }),
            );
          },
        );
      },
    );
  }

  Widget _filters() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_selected.isNotEmpty)
          FilledButton.icon(
            onPressed: _bulkSetPlan,
            icon: const Icon(Icons.workspace_premium),
            label: Text('Set plan (${_selected.length})'),
          ),
        TextField(
          controller: _search,
          textInputAction: TextInputAction.search,
          onChanged: (_) => _scheduleReload(),
          decoration: const InputDecoration(
            labelText: 'Search users',
            hintText: 'Email or name',
            prefixIcon: Icon(Icons.search),
          ),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _tier,
          decoration: const InputDecoration(
            labelText: 'Tier',
            prefixIcon: Icon(Icons.workspace_premium_outlined),
          ),
          items: [
            const DropdownMenuItem(value: 'all', child: Text('All tiers')),
            for (final t in kAdminTiers)
              DropdownMenuItem(value: t, child: Text(adminTierLabel(t))),
          ],
          onChanged: (value) {
            if (value == null || value == _tier) return;
            setState(() => _tier = value);
            _debounce?.cancel();
            _list.reload();
          },
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilterChip(
              key: const ValueKey('filter-suspended'),
              label: const Text('Suspended'),
              selected: _status == 'suspended',
              onSelected: (value) {
                setState(() => _status = value ? 'suspended' : 'all');
                _list.reload();
              },
            ),
            FilterChip(
              key: const ValueKey('filter-expiring'),
              label: const Text('Expiring soon'),
              selected: _expiringSoon,
              onSelected: (value) {
                setState(() => _expiringSoon = value);
                _list.reload();
              },
            ),
            ActionChip(
              label: Text(
                _testerLabel.isEmpty ? 'Tester label' : 'Tester: $_testerLabel',
              ),
              onPressed: () async {
                final value = await showDialog<String>(
                  context: context,
                  builder: (dialogContext) {
                    final controller = TextEditingController(
                      text: _testerLabel,
                    );
                    return AlertDialog(
                      title: const Text('Tester label'),
                      content: TextField(
                        controller: controller,
                        autofocus: true,
                        decoration: const InputDecoration(
                          hintText: 'Leave empty to clear',
                        ),
                      ),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(dialogContext),
                          child: const Text('Cancel'),
                        ),
                        FilledButton(
                          onPressed: () =>
                              Navigator.pop(dialogContext, controller.text),
                          child: const Text('Apply'),
                        ),
                      ],
                    );
                  },
                );
                if (value == null || !mounted) return;
                setState(() => _testerLabel = value.trim());
                _list.reload();
              },
            ),
          ],
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}

class _UserRow extends StatelessWidget {
  const _UserRow({
    required this.user,
    required this.selected,
    required this.onTap,
    required this.onLongPress,
  });

  final AdminUser user;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final status = user.disabled ? 'Suspended' : 'Active';
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: KarmiFocusRing(
        child: KarmiCard(
          semanticContainer: false,
          padding: EdgeInsets.zero,
          child: ListTile(
            minTileHeight: 48,
            onTap: onTap,
            onLongPress: onLongPress,
            leading: Checkbox(value: selected, onChanged: (_) => onLongPress()),
            title: Text(
              user.displayName.isEmpty ? user.email : user.displayName,
              style: text.titleMedium,
            ),
            subtitle: Text(
              '${user.email}\nTier: ${user.tier} · ${user.openBugReports} open bug ${user.openBugReports == 1 ? 'report' : 'reports'}',
              style: text.bodyMedium,
            ),
            isThreeLine: true,
            trailing: Semantics(
              label: 'Status: $status',
              excludeSemantics: true,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    user.disabled ? Icons.block : Icons.check_circle_outline,
                    size: 18,
                  ),
                  const SizedBox(width: 4),
                  Text(status, style: text.labelLarge),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
