import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../api/karmi_api.dart';
import '../auth/session.dart';
import '../armory/armory_controller.dart';
import '../features/armory/armory_screen.dart';
import '../features/chat/chat_screen.dart';
import '../features/plans/plan_selection_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/tasks/tasks_screen.dart';
import '../features/usage/usage_screen.dart';
import '../settings/karmi_settings.dart';
import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';
import '../theme/karmi_theme.dart';
import '../widgets/focus_ring.dart';
import 'history_panel.dart';
import 'chat_history_commands.dart';

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
  _Destination('Settings', Icons.settings_outlined, Icons.settings),
];

/// App shell (T3.1): four tabs. Glass app bar + tab bar normally; plain opaque
/// Material bars when reduce transparency / high contrast is on (§5.2).
/// Adapts responsively across compact, medium, and expanded breakpoints (§7 C).
class KarmiShell extends StatefulWidget {
  const KarmiShell({
    super.key,
    required this.api,
    required this.settings,
    required this.session,
    required this.armory,
    this.historyRailBuilder,
    this.historyCommands,
  });

  final KarmiApi api;
  final KarmiSettings settings;
  final KarmiSession session;
  final ArmoryController armory;
  final WidgetBuilder? historyRailBuilder;
  final ChatHistoryCommands? historyCommands;

  @override
  State<KarmiShell> createState() => _KarmiShellState();
}

class _KarmiShellState extends State<KarmiShell> {
  int _index = 0;
  final _bodyKey = GlobalKey();
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  final Set<int> _visited = {0};
  final List<Widget?> _pages = [null, null, null, null];
  @override
  void didUpdateWidget(KarmiShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.historyCommands != oldWidget.historyCommands) {
      _pages[0] = null;
    }
  }
  bool _isHistoryOverlayOpen = false;

  void _openHistory() {
    final width = MediaQuery.sizeOf(context).width;
    if (width < KarmiShape.tabletBreakpoint) {
      _scaffoldKey.currentState?.openDrawer();
    } else if (width < KarmiShape.desktopBreakpoint) {
      setState(() {
        _isHistoryOverlayOpen = true;
      });
    }
  }

  void _closeHistory() {
    if (_isHistoryOverlayOpen) {
      setState(() {
        _isHistoryOverlayOpen = false;
      });
    }
  }

  void _toggleHistory() {
    final width = MediaQuery.sizeOf(context).width;
    if (width < KarmiShape.tabletBreakpoint) {
      final state = _scaffoldKey.currentState;
      if (state != null) {
        if (state.isDrawerOpen) {
          Navigator.of(context).pop();
        } else {
          state.openDrawer();
        }
      }
    } else if (width < KarmiShape.desktopBreakpoint) {
      setState(() {
        _isHistoryOverlayOpen = !_isHistoryOverlayOpen;
      });
    }
  }

  void _openPlans() => Navigator.of(context).push(
    KarmiMotion.route<void>(
      context,
      (_) => PlanSelectionScreen(
        currentPlanId: widget.armory.unlockedTier.planId,
        api: widget.api,
        onPlanChanged: widget.armory.load,
      ),
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

  Widget _buildPage(int index) {
    switch (index) {
      case 0:
        return ChatScreen(
          api: widget.api,
          onOpenPlans: _openPlans,
          draftStore: widget.session.draftStore,
          historyCommands: widget.historyCommands,
        );
      case 1:
        return TasksScreen(api: widget.api);
      case 2:
        return UsageScreen(api: widget.api);
      case 3:
        return SettingsScreen(
          settings: widget.settings,
          session: widget.session,
          armory: widget.armory,
          onOpenArmory: _openArmory,
          onOpenPlans: _openPlans,
        );
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _pageFor(int index) {
    if (!_visited.contains(index)) {
      return const SizedBox.shrink();
    }
    return _pages[index] ??= _buildPage(index);
  }

  void _select(int index) {
    if (_isHistoryOverlayOpen) {
      setState(() {
        _isHistoryOverlayOpen = false;
      });
    }
    setState(() {
      _index = index;
      _visited.add(index);
    });
  }

  Widget _buildNavRail() {
    return Semantics(
      container: true,
      label: 'Main navigation',
      child: NavigationRail(
        selectedIndex: _index,
        onDestinationSelected: _select,
        labelType: NavigationRailLabelType.all,
        destinations: [
          for (final d in _destinations)
            NavigationRailDestination(
              icon: Semantics(label: '${d.label} tab', child: Icon(d.icon)),
              selectedIcon: Semantics(
                label: '${d.label} tab',
                child: Icon(d.selectedIcon),
              ),
              label: Text(d.label),
            ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context, Widget body) {
    final width = MediaQuery.sizeOf(context).width;
    final isCompactNav = width < 600;
    final isTablet = width >= KarmiShape.tabletBreakpoint &&
        width < KarmiShape.desktopBreakpoint;
    final isDesktop = width >= KarmiShape.desktopBreakpoint;

    Widget mainContent = body;
    if (isTablet && widget.historyRailBuilder != null) {
      mainContent = Stack(
        fit: StackFit.expand,
        children: [
          body,
          HistoryOverlay(
            isOpen: _isHistoryOverlayOpen,
            onClose: _closeHistory,
            child: widget.historyRailBuilder!(context),
          ),
        ],
      );
    }

    if (isCompactNav) {
      return mainContent;
    }

    final navRail = SizedBox(width: 80, child: _buildNavRail());

    if (isDesktop && widget.historyRailBuilder != null) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          navRail,
          HistoryPanel(
            width: KarmiShape.historyRailWidth,
            child: widget.historyRailBuilder!(context),
          ),
          Expanded(child: mainContent),
        ],
      );
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        navRail,
        Expanded(child: mainContent),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final title = Text(
      _destinations[_index].label,
      style: Theme.of(context).textTheme.titleMedium,
    );
    final body = IndexedStack(
      key: _bodyKey,
      index: _index,
      children: [for (var i = 0; i < 4; i++) _pageFor(i)],
    );

    final width = MediaQuery.sizeOf(context).width;
    final isCompactNav = width < 600;
    final isPhone = width < KarmiShape.tabletBreakpoint;
    final content = _buildContent(context, body);

    if (KarmiAccessibility.reduceTransparencyOf(context)) {
      return HistoryPanelScope(
        isOpen: _isHistoryOverlayOpen,
        openHistory: _openHistory,
        closeHistory: _closeHistory,
        toggleHistory: _toggleHistory,
        child: Scaffold(
          key: _scaffoldKey,
          drawer: isPhone && widget.historyRailBuilder != null
              ? HistoryDrawer(child: widget.historyRailBuilder!(context))
              : null,
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
          body: _withPreviewBanner(
            content,
            top: 8,
          ),
          bottomNavigationBar: isCompactNav
              ? NavigationBar(
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
                )
              : null,
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
      bottom: mq.padding.bottom + (isCompactNav ? tabBar.preferredSize.height : 0),
    );

    return HistoryPanelScope(
      isOpen: _isHistoryOverlayOpen,
      openHistory: _openHistory,
      closeHistory: _closeHistory,
      toggleHistory: _toggleHistory,
      child: Scaffold(
        key: _scaffoldKey,
        backgroundColor: Colors.transparent,
        drawer: isPhone && widget.historyRailBuilder != null
            ? HistoryDrawer(child: widget.historyRailBuilder!(context))
            : null,
        body: GlassScaffold(
          key: const ValueKey('shell-glass'),
          backgroundColor: KarmiColors.of(context).background,
          appBar: appBar,
          bottomBar: isCompactNav
              ? Semantics(
                  container: true,
                  label: 'Main navigation',
                  // GlassTabBar's own keyboard focus ring is not painted on device.
                  child: KarmiFocusRing(radius: 16, child: tabBar),
                )
              : null,
          bottomBarHeight: isCompactNav ? tabBar.preferredSize.height : 0,
          body: MediaQuery(
            data: mq.copyWith(padding: bodyPadding),
            child: IconTheme(
              data: Theme.of(context).iconTheme,
              child: _withPreviewBanner(
                content,
                top: bodyPadding.top + 8,
              ),
            ),
          ),
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
