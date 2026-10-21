import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/shell/breakpoints.dart';
import 'package:karmi_app/shell/workspace_layout.dart';

/// A probe widget that counts how many times its State is built.
class _ProbePage extends StatefulWidget {
  const _ProbePage({
    required this.label,
    this.onInit,
    this.onBuilt,
  });

  final String label;
  final VoidCallback? onInit;
  final VoidCallback? onBuilt;

  @override
  State<_ProbePage> createState() => _ProbePageState();
}

class _ProbePageState extends State<_ProbePage> {
  @override
  void initState() {
    super.initState();
    widget.onInit?.call();
  }

  @override
  Widget build(BuildContext context) {
    widget.onBuilt?.call();
    return Center(child: Text(widget.label));
  }
}

/// Harness replicating KarmiShell's lazy tab and responsive WorkspaceLayout
/// pattern without transitively importing ChatScreen (which awaits Phase 2 wiring).
class _TestLazyResponsiveShell extends StatefulWidget {
  const _TestLazyResponsiveShell({
    required this.tabBuilders,
    this.historyRailBuilder,
  });

  final List<WidgetBuilder> tabBuilders;
  final WidgetBuilder? historyRailBuilder;

  @override
  State<_TestLazyResponsiveShell> createState() =>
      _TestLazyResponsiveShellState();
}

class _TestLazyResponsiveShellState extends State<_TestLazyResponsiveShell> {
  int _index = 0;
  final _bodyKey = GlobalKey();
  final Set<int> _visited = {0};
  late final List<Widget?> _pages = List.filled(widget.tabBuilders.length, null);

  Widget _pageFor(int index) {
    if (!_visited.contains(index)) {
      return const SizedBox.shrink();
    }
    return _pages[index] ??= widget.tabBuilders[index](context);
  }

  void _select(int index) {
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
        destinations: const [
          NavigationRailDestination(
            icon: Icon(Icons.chat_bubble_outline),
            selectedIcon: Icon(Icons.chat_bubble),
            label: Text('Chat'),
          ),
          NavigationRailDestination(
            icon: Icon(Icons.check_box_outlined),
            selectedIcon: Icon(Icons.check_box),
            label: Text('Tasks'),
          ),
          NavigationRailDestination(
            icon: Icon(Icons.data_usage),
            selectedIcon: Icon(Icons.data_usage),
            label: Text('Usage'),
          ),
          NavigationRailDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: Text('Settings'),
          ),
        ],
      ),
    );
  }

  Widget _buildRail(BuildContext context, WorkspaceSize size) {
    final navRail = _buildNavRail();
    if (size == WorkspaceSize.expanded && widget.historyRailBuilder != null) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          navRail,
          Expanded(child: widget.historyRailBuilder!(context)),
        ],
      );
    }
    return navRail;
  }

  @override
  Widget build(BuildContext context) {
    final body = IndexedStack(
      key: _bodyKey,
      index: _index,
      children: [
        for (var i = 0; i < widget.tabBuilders.length; i++) _pageFor(i),
      ],
    );

    final workspaceSize = workspaceSizeOfContext(context);
    final isCompact = workspaceSize == WorkspaceSize.compact;

    return Scaffold(
      body: isCompact
          ? body
          : WorkspaceLayout(
              rail: _buildRail(context, workspaceSize),
              main: body,
            ),
      bottomNavigationBar: isCompact
          ? NavigationBar(
              selectedIndex: _index,
              onDestinationSelected: _select,
              destinations: const [
                NavigationDestination(
                  icon: Icon(Icons.chat_bubble_outline),
                  selectedIcon: Icon(Icons.chat_bubble),
                  label: 'Chat',
                ),
                NavigationDestination(
                  icon: Icon(Icons.check_box_outlined),
                  selectedIcon: Icon(Icons.check_box),
                  label: 'Tasks',
                ),
                NavigationDestination(
                  icon: Icon(Icons.data_usage),
                  selectedIcon: Icon(Icons.data_usage),
                  label: 'Usage',
                ),
                NavigationDestination(
                  icon: Icon(Icons.settings_outlined),
                  selectedIcon: Icon(Icons.settings),
                  label: 'Settings',
                ),
              ],
            )
          : null,
    );
  }
}

void main() {
  group('Lazy tabs probe tests', () {
    testWidgets('probe page counts builds only after first visit', (
      tester,
    ) async {
      var tab0Builds = 0;
      var tab1Builds = 0;
      var tab2Builds = 0;
      var tab3Builds = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: _TestLazyResponsiveShell(
            tabBuilders: [
              (_) => _ProbePage(label: 'Chat Tab', onBuilt: () => tab0Builds++),
              (_) => _ProbePage(label: 'Tasks Tab', onBuilt: () => tab1Builds++),
              (_) => _ProbePage(label: 'Usage Tab', onBuilt: () => tab2Builds++),
              (_) => _ProbePage(label: 'Settings Tab', onBuilt: () => tab3Builds++),
            ],
          ),
        ),
      );

      // On initial pump: only tab 0 is built. Tabs 1, 2, 3 have 0 builds.
      expect(tab0Builds, 1);
      expect(tab1Builds, 0);
      expect(tab2Builds, 0);
      expect(tab3Builds, 0);
      expect(find.text('Chat Tab'), findsOneWidget);
      expect(find.text('Tasks Tab'), findsNothing);

      // Tap on Tasks tab (tab 1)
      await tester.tap(find.text('Tasks'));
      await tester.pumpAndSettle();

      // Tab 1 is built for the first time; tabs 2 and 3 remain unvisited.
      expect(tab0Builds, 1);
      expect(tab1Builds, 1);
      expect(tab2Builds, 0);
      expect(tab3Builds, 0);
      expect(find.text('Tasks Tab'), findsOneWidget);

      // Tap on Usage tab (tab 2)
      await tester.tap(find.text('Usage'));
      await tester.pumpAndSettle();

      expect(tab0Builds, 1);
      expect(tab1Builds, 1);
      expect(tab2Builds, 1);
      expect(tab3Builds, 0);
      expect(find.text('Usage Tab'), findsOneWidget);

      // Switch back to Chat tab (tab 0): widget identity is stable, build count remains 1
      await tester.tap(find.text('Chat'));
      await tester.pumpAndSettle();

      expect(tab0Builds, 1);
      expect(tab1Builds, 1);
      expect(tab2Builds, 1);
      expect(tab3Builds, 0);
      expect(find.text('Chat Tab'), findsOneWidget);
    });
  });

  group('Responsive workspace layout with shell', () {
    testWidgets('compact (<600) shows NavigationBar and no NavigationRail', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(400, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        MaterialApp(
          home: _TestLazyResponsiveShell(
            tabBuilders: [
              (_) => const Text('Page 0'),
              (_) => const Text('Page 1'),
              (_) => const Text('Page 2'),
              (_) => const Text('Page 3'),
            ],
          ),
        ),
      );

      expect(find.byType(NavigationBar), findsOneWidget);
      expect(find.byType(NavigationRail), findsNothing);
      expect(find.text('Page 0'), findsOneWidget);
    });

    testWidgets('medium (600..1024) shows NavigationRail and no bottom bar', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(800, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        MaterialApp(
          home: _TestLazyResponsiveShell(
            tabBuilders: [
              (_) => const Text('Page 0'),
              (_) => const Text('Page 1'),
              (_) => const Text('Page 2'),
              (_) => const Text('Page 3'),
            ],
          ),
        ),
      );

      expect(find.byType(NavigationBar), findsNothing);
      expect(find.byType(NavigationRail), findsOneWidget);
      expect(find.text('Page 0'), findsOneWidget);
    });

    testWidgets(
      'expanded (>1024) with historyRailBuilder embeds history rail alongside NavigationRail',
      (tester) async {
        tester.view.physicalSize = const Size(1200, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);

        await tester.pumpWidget(
          MaterialApp(
            home: _TestLazyResponsiveShell(
              historyRailBuilder: (context) => const Text('HISTORY_RAIL'),
              tabBuilders: [
                (_) => const Text('Page 0'),
                (_) => const Text('Page 1'),
                (_) => const Text('Page 2'),
                (_) => const Text('Page 3'),
              ],
            ),
          ),
        );

        expect(find.byType(NavigationBar), findsNothing);
        expect(find.byType(NavigationRail), findsOneWidget);
        expect(find.text('HISTORY_RAIL'), findsOneWidget);
        expect(find.text('Page 0'), findsOneWidget);
        expect(find.byType(VerticalDivider), findsOneWidget);
      },
    );

    testWidgets('preserves tab state across resize from compact to expanded', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(400, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      var initCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: _TestLazyResponsiveShell(
            tabBuilders: [
              (_) => _ProbePage(label: 'Chat Content', onInit: () => initCount++),
              (_) => const Text('Tasks'),
              (_) => const Text('Usage'),
              (_) => const Text('Settings'),
            ],
          ),
        ),
      );

      expect(initCount, 1);
      expect(find.text('Chat Content'), findsOneWidget);

      // Resize to desktop (1200)
      tester.view.physicalSize = const Size(1200, 800);
      await tester.pumpAndSettle();

      expect(find.byType(NavigationRail), findsOneWidget);
      expect(find.text('Chat Content'), findsOneWidget);
      // State was preserved: initState was called only once (State object preserved)
      expect(initCount, 1);
    });
  });
}
