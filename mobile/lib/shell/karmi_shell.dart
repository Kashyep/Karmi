import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../api/karmi_api.dart';
import '../auth/session.dart';
import '../armory/armory_controller.dart';
import '../features/armory/armory_screen.dart';
import '../features/chat/chat_screen.dart';
import '../features/memory/memory_screen.dart';
import '../features/plans/plan_selection_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/tasks/tasks_screen.dart';
import '../features/usage/usage_screen.dart';
import '../settings/karmi_settings.dart';
import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';
import '../widgets/focus_ring.dart';

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
    required this.armory,
  });

  final KarmiApi api;
  final KarmiSettings settings;
  final KarmiSession session;
  final ArmoryController armory;

  @override
  State<KarmiShell> createState() => _KarmiShellState();
}

class _KarmiShellState extends State<KarmiShell> {
  int _index = 0;

  void _openPlans() => Navigator.of(context).push(
    KarmiMotion.route<void>(
      context,
      (_) =>
          PlanSelectionScreen(currentPlanId: widget.armory.unlockedTier.planId),
    ),
  );

  void _openArmory() => Navigator.of(context).push(
    KarmiMotion.route<void>(
      context,
      (_) => ArmoryScreen(armory: widget.armory),
    ),
  );

  void _openLicences() =>
      showLicensePage(context: context, applicationName: 'Karmi');

  late final List<Widget> _pages = [
    ChatScreen(api: widget.api, onOpenPlans: _openPlans),
    TasksScreen(api: widget.api),
    UsageScreen(api: widget.api),
    MemoryScreen(api: widget.api),
    SettingsScreen(
      settings: widget.settings,
      session: widget.session,
      armory: widget.armory,
      onOpenArmory: _openArmory,
    ),
  ];

  /// Keeps tab state (e.g. the chat transcript) when the shell switches between
  /// the glass and the opaque scaffold (reduce transparency / high contrast).
  final _bodyKey = GlobalKey();

  void _select(int index) => setState(() => _index = index);

  @override
  Widget build(BuildContext context) {
    final title = Text(
      _destinations[_index].label,
      style: Theme.of(context).textTheme.titleMedium,
    );
    final body = IndexedStack(key: _bodyKey, index: _index, children: _pages);

    if (KarmiAccessibility.reduceTransparencyOf(context)) {
      return Scaffold(
        key: const ValueKey('shell-opaque'),
        appBar: AppBar(
          title: Semantics(header: true, child: title),
          actions: [
            _OverflowMenu(
              onArmory: _openArmory,
              onPlans: _openPlans,
              onLicences: _openLicences,
            ),
          ],
        ),
        body: _withPreviewBanner(body, top: 8),
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
      backgroundColor: KarmiColors.of(context).glassBase,
      title: Semantics(header: true, child: title),
      // Material menu, not GlassMenu: on device GlassMenu's items were
      // missing from the accessibility tree (TalkBack could not reach them).
      actions: [
        _OverflowMenu(
          onArmory: _openArmory,
          onPlans: _openPlans,
          onLicences: _openLicences,
        ),
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
        // GlassTabBar's own keyboard focus ring is not painted on device.
        child: KarmiFocusRing(radius: 16, child: tabBar),
      ),
      bottomBarHeight: tabBar.preferredSize.height,
      body: MediaQuery(
        data: mq.copyWith(padding: bodyPadding),
        // GlassScaffold installs a Cupertino IconTheme (primary colour) that
        // IconButton adopts as its foreground; restore the Material one so
        // controls look the same as in the opaque shell.
        child: IconTheme(
          data: Theme.of(context).iconTheme,
          child: _withPreviewBanner(body, top: bodyPadding.top + 8),
        ),
      ),
    );
  }

  /// While a locked tier is previewed, the countdown banner floats over every
  /// tab so the user can explore the whole app in that theme.
  Widget _withPreviewBanner(Widget body, {required double top}) =>
      ListenableBuilder(
        listenable: widget.armory,
        builder: (context, child) => Stack(
          children: [
            child!,
            if (widget.armory.isPreviewing)
              Positioned(
                top: top,
                left: 12,
                right: 12,
                child: ArmoryPreviewBanner(armory: widget.armory),
              ),
          ],
        ),
        child: body,
      );
}

class _OverflowMenu extends StatelessWidget {
  const _OverflowMenu({
    required this.onArmory,
    required this.onPlans,
    required this.onLicences,
  });

  final VoidCallback onArmory;
  final VoidCallback onPlans;
  final VoidCallback onLicences;

  @override
  Widget build(BuildContext context) => PopupMenuButton<VoidCallback>(
    tooltip: 'More options',
    onSelected: (action) => action(),
    itemBuilder: (context) => [
      PopupMenuItem(value: onArmory, child: const Text('Armory')),
      PopupMenuItem(value: onPlans, child: const Text('Plans')),
      PopupMenuItem(value: onLicences, child: const Text('Licences')),
    ],
  );
}
