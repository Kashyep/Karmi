import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import 'admin_controller.dart';
import 'admin_support.dart';
import 'audit_screen.dart';
import 'monitor_screen.dart';
import 'users_screen.dart';

enum AdminSection {
  users('Users', Icons.people_outline, Icons.people),
  monitor('Monitor', Icons.monitor_heart_outlined, Icons.monitor_heart),
  audit('Audit', Icons.fact_check_outlined, Icons.fact_check);

  const AdminSection(this.label, this.icon, this.selectedIcon);

  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

/// The only UI shown while an admin session is active. Wide layouts use a
/// NavigationRail; narrow layouts use a bottom NavigationBar.
class AdminShell extends StatefulWidget {
  const AdminShell({super.key, required this.controller});

  final AdminController controller;

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  AdminSection _section = AdminSection.users;

  Future<void> _logout() => widget.controller.logout();

  Widget _body() {
    final controller = widget.controller;
    return switch (_section) {
      AdminSection.users => UsersScreen(
        key: const ValueKey('admin-users'),
        controller: controller,
      ),
      AdminSection.monitor => MonitorScreen(
        key: const ValueKey('admin-monitor'),
        controller: controller,
      ),
      AdminSection.audit => AuditScreen(
        key: const ValueKey('admin-audit'),
        controller: controller,
      ),
    };
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.controller,
      builder: (context, _) {
        // Session ended (expiry, 401, logout): the app swaps back to the
        // normal shell, so render nothing here.
        if (widget.controller.token == null) return const SizedBox.shrink();
        return LayoutBuilder(
          builder: (context, constraints) {
            final wide = constraints.maxWidth >= kAdminWideBreakpoint;
            final colors = KarmiColors.of(context);
            final content = Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _Header(onLogout: _logout),
                Expanded(child: _body()),
              ],
            );
            if (wide) {
              return Scaffold(
                backgroundColor: colors.background,
                body: SafeArea(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      NavigationRail(
                        selectedIndex: _section.index,
                        labelType: NavigationRailLabelType.all,
                        onDestinationSelected: _select,
                        destinations: [
                          for (final s in AdminSection.values)
                            NavigationRailDestination(
                              icon: Icon(s.icon),
                              selectedIcon: Icon(s.selectedIcon),
                              label: Text(s.label),
                            ),
                        ],
                      ),
                      const VerticalDivider(width: 1),
                      Expanded(child: content),
                    ],
                  ),
                ),
              );
            }
            return Scaffold(
              backgroundColor: colors.background,
              body: SafeArea(child: content),
              bottomNavigationBar: NavigationBar(
                selectedIndex: _section.index,
                onDestinationSelected: _select,
                destinations: [
                  for (final s in AdminSection.values)
                    NavigationDestination(
                      icon: Icon(s.icon),
                      selectedIcon: Icon(s.selectedIcon),
                      label: s.label,
                    ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _select(int index) {
    setState(() => _section = AdminSection.values[index]);
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.onLogout});

  final Future<void> Function() onLogout;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        alignment: WrapAlignment.spaceBetween,
        children: [
          Semantics(
            header: true,
            child: Text('Admin console', style: text.headlineSmall),
          ),
          OutlinedButton.icon(
            style: kAdminButtonStyle,
            onPressed: onLogout,
            icon: const Icon(Icons.logout, size: 18),
            label: const Text('Log out of admin'),
          ),
        ],
      ),
    );
  }
}
