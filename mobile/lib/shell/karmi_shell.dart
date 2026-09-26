import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../api/karmi_api.dart';
import '../auth/session.dart';
import '../features/chat/chat_screen.dart';
import '../features/memory/memory_screen.dart';
import '../features/plans/plan_selection_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/tasks/tasks_screen.dart';
import '../features/usage/usage_screen.dart';
import '../settings/karmi_settings.dart';
import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';

class _Destination {
  const _Destination(this.label, this.icon, this.selectedIcon);

  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

const _destinations = [
  _Destination('Chat', Icons.chat_bubble_outline, Icons.chat_bubble),
  _Destination('Tasks', Icons.check_box_outlined, Icons.check_box),
  _Destination('Usage', Icons.data_usage, Icons.data_usage),
  _Destination('Memory', Icons.bookmark_border, Icons.bookmark),
  _Destination('Settings', Icons.settings_outlined, Icons.settings),
];

/// App shell (T3.1): five tabs. Glass app bar + tab bar normally; plain opaque
/// Material bars when reduce transparency / high contrast is on (§5.2).
class KarmiShell extends StatefulWidget {
  const KarmiShell({
    super.key,
    required this.api,
    required this.settings,
    required this.session,
  });

  final KarmiApi api;
  final KarmiSettings settings;
  final KarmiSession session;

  @override
  State<KarmiShell> createState() => _KarmiShellState();
}

class _KarmiShellState extends State<KarmiShell> {
  int _index = 0;

  void _openPlans() => Navigator.of(
    context,
  ).push(KarmiMotion.route<void>(context, (_) => const PlanSelectionScreen()));

  void _openLicences() =>
      showLicensePage(context: context, applicationName: 'Karmi');

  late final List<Widget> _pages = [
    ChatScreen(api: widget.api, onOpenPlans: _openPlans),
    TasksScreen(api: widget.api),
    UsageScreen(api: widget.api),
    MemoryScreen(api: widget.api),
    SettingsScreen(settings: widget.settings, session: widget.session),
  ];

  void _select(int index) => setState(() => _index = index);

  @override
  Widget build(BuildContext context) {
    final title = Text(
      _destinations[_index].label,
      style: Theme.of(context).textTheme.titleMedium,
    );
    final body = IndexedStack(index: _index, children: _pages);

    if (KarmiAccessibility.reduceTransparencyOf(context)) {
      return Scaffold(
        key: const ValueKey('shell-opaque'),
        appBar: AppBar(
          title: Semantics(header: true, child: title),
          actions: [
            _OpaqueMenu(onPlans: _openPlans, onLicences: _openLicences),
          ],
        ),
        body: body,
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: _select,
          destinations: [
            for (final d in _destinations)
              NavigationDestination(
                icon: Icon(d.icon),
                selectedIcon: Icon(d.selectedIcon),
                label: d.label,
              ),
          ],
        ),
      );
    }

    final appBar = GlassAppBar(
      title: Semantics(header: true, child: title),
      actions: [
        _GlassOverflowMenu(onPlans: _openPlans, onLicences: _openLicences),
      ],
    );
    final tabBar = GlassTabBar.bottom(
      selectedIndex: _index,
      onTabSelected: _select,
      tabs: [
        for (final d in _destinations)
          GlassTab(
            icon: Icon(d.icon),
            activeIcon: Icon(d.selectedIcon),
            label: d.label,
            semanticLabel: '${d.label} tab',
          ),
      ],
    );

    // The glass bars float over the body; report their extent as padding so
    // content can scroll behind them without being hidden at rest.
    final mq = MediaQuery.of(context);
    final bodyPadding = mq.padding.copyWith(
      top: mq.padding.top + appBar.preferredSize.height,
      bottom: mq.padding.bottom + tabBar.preferredSize.height,
    );

    return GlassScaffold(
      key: const ValueKey('shell-glass'),
      backgroundColor: KarmiColors.of(context).background,
      appBar: appBar,
      // The bar-level drag/tap detector inside GlassTabBar exposes an
      // unlabelled tap node; this container gives it a name for TalkBack /
      // VoiceOver (labeledTapTargetGuideline). Each tab keeps its own label.
      bottomBar: Semantics(
        container: true,
        label: 'Main navigation',
        child: tabBar,
      ),
      bottomBarHeight: tabBar.preferredSize.height,
      body: MediaQuery(
        data: mq.copyWith(padding: bodyPadding),
        child: body,
      ),
    );
  }
}

class _GlassOverflowMenu extends StatelessWidget {
  const _GlassOverflowMenu({required this.onPlans, required this.onLicences});

  final VoidCallback onPlans;
  final VoidCallback onLicences;

  @override
  Widget build(BuildContext context) {
    final fg = KarmiColors.of(context).foreground;
    return GlassMenu(
      menuWidth: 220,
      trigger: Semantics(
        button: true,
        label: 'More options',
        child: SizedBox.square(
          dimension: 48,
          child: Icon(Icons.more_vert, color: fg),
        ),
      ),
      items: [
        GlassMenuItem(
          height: 48,
          icon: const Icon(Icons.workspace_premium_outlined),
          title: 'Plans',
          onTap: onPlans,
        ),
        GlassMenuItem(
          height: 48,
          icon: const Icon(Icons.description_outlined),
          title: 'Licences',
          onTap: onLicences,
        ),
      ],
    );
  }
}

class _OpaqueMenu extends StatelessWidget {
  const _OpaqueMenu({required this.onPlans, required this.onLicences});

  final VoidCallback onPlans;
  final VoidCallback onLicences;

  @override
  Widget build(BuildContext context) => PopupMenuButton<VoidCallback>(
    tooltip: 'More options',
    onSelected: (action) => action(),
    itemBuilder: (context) => [
      PopupMenuItem(value: onPlans, child: const Text('Plans')),
      PopupMenuItem(value: onLicences, child: const Text('Licences')),
    ],
  );
}
