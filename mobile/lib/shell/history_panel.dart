import 'package:flutter/material.dart';

import '../theme/karmi_colors.dart';
import '../theme/karmi_motion.dart';
import '../theme/karmi_theme.dart';

/// Scope exposing history open/close actions to descendant widgets (§3.1, §5.7).
class HistoryPanelScope extends InheritedWidget {
  const HistoryPanelScope({
    super.key,
    required this.isOpen,
    required this.openHistory,
    required this.closeHistory,
    required this.toggleHistory,
    required super.child,
  });

  final bool isOpen;
  final VoidCallback openHistory;
  final VoidCallback closeHistory;
  final VoidCallback toggleHistory;

  static HistoryPanelScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<HistoryPanelScope>();

  static HistoryPanelScope of(BuildContext context) {
    final scope = maybeOf(context);
    assert(scope != null, 'No HistoryPanelScope found in context');
    return scope!;
  }

  /// Convenience opener that opens the history overlay or drawer.
  /// Returns `true` if handled.
  static bool open(BuildContext context) {
    final scope = maybeOf(context);
    if (scope != null) {
      scope.openHistory();
      return true;
    }
    final scaffold = Scaffold.maybeOf(context);
    if (scaffold != null && scaffold.hasDrawer) {
      scaffold.openDrawer();
      return true;
    }
    return false;
  }

  /// Convenience closer that closes the history overlay or drawer.
  /// Returns `true` if handled.
  static bool close(BuildContext context) {
    final scope = maybeOf(context);
    if (scope != null && scope.isOpen) {
      scope.closeHistory();
      return true;
    }
    final scaffold = Scaffold.maybeOf(context);
    if (scaffold != null && scaffold.isDrawerOpen) {
      Navigator.of(context).pop();
      return true;
    }
    return false;
  }

  @override
  bool updateShouldNotify(HistoryPanelScope oldWidget) =>
      isOpen != oldWidget.isOpen || openHistory != oldWidget.openHistory;
}

/// History rail panel container (§3.1, §5.7).
///
/// Features a recessed solid [sidebarSurface] background and a 1px [hairline]
/// divider along the right edge.
class HistoryPanel extends StatelessWidget {
  const HistoryPanel({
    super.key,
    required this.child,
    this.width = KarmiShape.historyRailWidth,
    this.showBorder = true,
  });

  final Widget child;
  final double width;
  final bool showBorder;

  /// Shorthand to trigger history open via [HistoryPanelScope].
  static bool open(BuildContext context) => HistoryPanelScope.open(context);

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);

    return Semantics(
      container: true,
      label: 'Conversation history',
      child: Container(
        width: width,
        decoration: BoxDecoration(
          color: colors.sidebarSurface,
          border: showBorder
              ? Border(
                  right: BorderSide(
                    color: colors.hairline,
                    width: 1,
                  ),
                )
              : null,
        ),
        child: child,
      ),
    );
  }
}

/// Tablet history overlay (768..1023px; §3.1, §5.7).
///
/// Slid over the body with a dismissible scrim background.
class HistoryOverlay extends StatelessWidget {
  const HistoryOverlay({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.child,
    this.width = KarmiShape.historyRailWidth,
  });

  final bool isOpen;
  final VoidCallback onClose;
  final Widget child;
  final double width;

  @override
  Widget build(BuildContext context) {
    final d = KarmiMotion.duration(context);

    return Stack(
      fit: StackFit.expand,
      children: [
        // Scrim
        IgnorePointer(
          ignoring: !isOpen,
          child: AnimatedOpacity(
            key: const ValueKey('history-overlay-scrim'),
            duration: d,
            opacity: isOpen ? 1.0 : 0.0,
            child: GestureDetector(
              onTap: onClose,
              behavior: HitTestBehavior.opaque,
              child: Container(
                color: Colors.black.withValues(alpha: 0.4),
              ),
            ),
          ),
        ),
        // Slid-in panel
        AnimatedPositioned(
          key: const ValueKey('history-overlay-panel'),
          duration: d,
          curve: Curves.easeOutCubic,
          left: isOpen ? 0 : -width,
          top: 0,
          bottom: 0,
          width: width,
          child: Material(
            elevation: 8,
            color: Colors.transparent,
            child: HistoryPanel(
              width: width,
              child: child,
            ),
          ),
        ),
      ],
    );
  }
}

/// Phone history drawer (<768px; §3.1, §5.7).
///
/// Drawer containing conversation history list for small screens.
class HistoryDrawer extends StatelessWidget {
  const HistoryDrawer({
    super.key,
    required this.child,
    this.width = KarmiShape.historyRailWidth,
  });

  final Widget child;
  final double width;

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: KarmiColors.of(context).sidebarSurface,
      width: width,
      child: SafeArea(
        child: child,
      ),
    );
  }
}
