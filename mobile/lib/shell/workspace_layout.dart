import 'package:flutter/material.dart';

import 'breakpoints.dart';

/// Pure responsive layout widget (§7 C) for Karmi workspace panes.
///
/// - Compact (<600): returns [main] only (shell handles drawer / bottom bar).
/// - Medium (600..1024): [Row] of NavigationRail-width (80) [rail] slot + [Expanded] [main].
/// - Expanded (>1024): [Row] of fixed-width history rail slot (300) with a
///   [VerticalDivider] using [ColorScheme.outline] + [Expanded] [main].
class WorkspaceLayout extends StatelessWidget {
  const WorkspaceLayout({super.key, required this.rail, required this.main});

  final Widget rail;
  final Widget main;

  @override
  Widget build(BuildContext context) {
    final size = workspaceSizeOfContext(context);
    switch (size) {
      case WorkspaceSize.compact:
        return main;
      case WorkspaceSize.medium:
        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(width: 80, child: rail),
            Expanded(child: main),
          ],
        );
      case WorkspaceSize.expanded:
        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(width: 300, child: rail),
            VerticalDivider(
              width: 1,
              thickness: 1,
              color: Theme.of(context).colorScheme.outline,
            ),
            Expanded(child: main),
          ],
        );
    }
  }
}
