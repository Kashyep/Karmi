import 'dart:async';

import 'package:flutter/material.dart';

import '../../widgets/focus_ring.dart';
import '../../widgets/karmi_card.dart';
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
  Timer? _debounce;
  late final PagedAdminList<AdminUser> _list = PagedAdminList(
    controller: widget.controller,
    fetch: (api, token, cursor) async {
      final q = _search.text.trim();
      final page = await api.listUsers(
        token,
        q: q.isEmpty ? null : q,
        tier: _tier == 'all' ? null : _tier,
        status: _status == 'all' ? null : _status,
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
        builder: (_) => UserDetailScreen(
          controller: widget.controller,
          userId: user.id,
        ),
      ),
    );
    if (changed == true) _list.reload();
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
              onTap: () => _open(items[index - 1]),
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
        DropdownButtonFormField<String>(
          initialValue: _status,
          decoration: const InputDecoration(
            labelText: 'Status',
            prefixIcon: Icon(Icons.filter_alt_outlined),
          ),
          items: const [
            DropdownMenuItem(value: 'all', child: Text('All statuses')),
            DropdownMenuItem(value: 'active', child: Text('Active')),
            DropdownMenuItem(value: 'suspended', child: Text('Suspended')),
          ],
          onChanged: (value) {
            if (value == null || value == _status) return;
            setState(() => _status = value);
            _debounce?.cancel();
            _list.reload();
          },
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}

class _UserRow extends StatelessWidget {
  const _UserRow({required this.user, required this.onTap});

  final AdminUser user;
  final VoidCallback onTap;

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
            title: Text(
              user.displayName.isEmpty ? user.email : user.displayName,
              style: text.titleMedium,
            ),
            subtitle: Text(
              '${user.email}\nTier: ${user.tier}',
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
                    user.disabled
                        ? Icons.block
                        : Icons.check_circle_outline,
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
