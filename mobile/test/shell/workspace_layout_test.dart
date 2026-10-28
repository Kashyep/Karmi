import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/shell/breakpoints.dart';
import 'package:karmi_app/shell/workspace_layout.dart';

void main() {
  group('Workspace breakpoints', () {
    test('workspaceSizeOf boundary classification', () {
      expect(workspaceSizeOf(0), WorkspaceSize.compact);
      expect(workspaceSizeOf(599.0), WorkspaceSize.compact);
      expect(workspaceSizeOf(599.99), WorkspaceSize.compact);
      expect(workspaceSizeOf(600.0), WorkspaceSize.medium);
      expect(workspaceSizeOf(800.0), WorkspaceSize.medium);
      expect(workspaceSizeOf(1024.0), WorkspaceSize.medium);
      expect(workspaceSizeOf(1024.01), WorkspaceSize.expanded);
      expect(workspaceSizeOf(1025.0), WorkspaceSize.expanded);
      expect(workspaceSizeOf(1920.0), WorkspaceSize.expanded);
    });

    test('WorkspaceSize static helper methods', () {
      expect(WorkspaceSize.workspaceSizeOf(599), WorkspaceSize.compact);
      expect(WorkspaceSize.workspaceSizeOf(600), WorkspaceSize.medium);
      expect(WorkspaceSize.workspaceSizeOf(1024), WorkspaceSize.medium);
      expect(WorkspaceSize.workspaceSizeOf(1025), WorkspaceSize.expanded);
    });

    testWidgets('workspaceSizeOfContext reads MediaQuery size', (tester) async {
      WorkspaceSize? capturedSize;
      final probe = Builder(
        builder: (context) {
          capturedSize = workspaceSizeOfContext(context);
          return const SizedBox.shrink();
        },
      );

      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(599, 800)),
          child: probe,
        ),
      );
      expect(capturedSize, WorkspaceSize.compact);

      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(600, 800)),
          child: probe,
        ),
      );
      expect(capturedSize, WorkspaceSize.medium);

      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(1024, 800)),
          child: probe,
        ),
      );
      expect(capturedSize, WorkspaceSize.medium);

      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(1025, 800)),
          child: probe,
        ),
      );
      expect(capturedSize, WorkspaceSize.expanded);
    });
  });

  group('WorkspaceLayout', () {
    testWidgets('compact width (400) renders main only', (tester) async {
      tester.view.physicalSize = const Size(400, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: WorkspaceLayout(
              rail: KeyedSubtree(
                key: ValueKey('test-rail'),
                child: Text('RAIL'),
              ),
              main: KeyedSubtree(
                key: ValueKey('test-main'),
                child: Text('MAIN'),
              ),
            ),
          ),
        ),
      );

      expect(find.byKey(const ValueKey('test-main')), findsOneWidget);
      expect(find.byKey(const ValueKey('test-rail')), findsNothing);
      expect(find.text('MAIN'), findsOneWidget);
      expect(find.text('RAIL'), findsNothing);
      expect(find.byType(VerticalDivider), findsNothing);
    });

    testWidgets(
      'medium width (800) renders rail in 80px slot and Expanded main',
      (tester) async {
        tester.view.physicalSize = const Size(800, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);

        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: WorkspaceLayout(
                rail: KeyedSubtree(
                  key: ValueKey('test-rail'),
                  child: Text('RAIL'),
                ),
                main: KeyedSubtree(
                  key: ValueKey('test-main'),
                  child: Text('MAIN'),
                ),
              ),
            ),
          ),
        );

        expect(find.byKey(const ValueKey('test-rail')), findsOneWidget);
        expect(find.byKey(const ValueKey('test-main')), findsOneWidget);

        final railSizedBox = tester.widget<SizedBox>(
          find
              .ancestor(
                of: find.byKey(const ValueKey('test-rail')),
                matching: find.byType(SizedBox),
              )
              .first,
        );
        expect(railSizedBox.width, 80.0);

        final mainFinder = find.byKey(const ValueKey('test-main'));
        expect(
          find.ancestor(of: mainFinder, matching: find.byType(Expanded)),
          findsOneWidget,
        );
        expect(find.byType(VerticalDivider), findsNothing);
      },
    );

    testWidgets(
      'expanded width (1200) renders rail in 300px slot with vertical divider',
      (tester) async {
        tester.view.physicalSize = const Size(1200, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);

        final testTheme = ThemeData(
          useMaterial3: true,
          colorScheme: const ColorScheme.light(outline: Colors.indigo),
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: testTheme,
            home: const Scaffold(
              body: WorkspaceLayout(
                rail: KeyedSubtree(
                  key: ValueKey('test-rail'),
                  child: Text('RAIL'),
                ),
                main: KeyedSubtree(
                  key: ValueKey('test-main'),
                  child: Text('MAIN'),
                ),
              ),
            ),
          ),
        );

        expect(find.byKey(const ValueKey('test-rail')), findsOneWidget);
        expect(find.byKey(const ValueKey('test-main')), findsOneWidget);

        final railSizedBox = tester.widget<SizedBox>(
          find
              .ancestor(
                of: find.byKey(const ValueKey('test-rail')),
                matching: find.byType(SizedBox),
              )
              .first,
        );
        expect(railSizedBox.width, 300.0);

        final divider = tester.widget<VerticalDivider>(
          find.byType(VerticalDivider),
        );
        expect(divider.color, Colors.indigo);
        expect(divider.width, 1.0);
        expect(divider.thickness, 1.0);

        final mainFinder = find.byKey(const ValueKey('test-main'));
        expect(
          find.ancestor(of: mainFinder, matching: find.byType(Expanded)),
          findsOneWidget,
        );
      },
    );
  });
}
