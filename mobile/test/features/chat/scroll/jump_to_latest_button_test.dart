import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/scroll/jump_to_latest_button.dart';

void main() {
  group('JumpToLatestButton', () {
    testWidgets('hidden when visible false (not found by tap / semantics excluded)', (tester) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: JumpToLatestButton(
              visible: false,
              onTap: () => tapped = true,
            ),
          ),
        ),
      );

      // Semantics is excluded when visible is false
      expect(find.bySemanticsLabel('Jump to latest message'), findsNothing);
      expect(find.bySemanticsLabel('New messages, jump to latest'), findsNothing);

      // Not hit-testable when ignored/hidden
      expect(
        find.byWidgetPredicate((w) => w is JumpToLatestButton).hitTestable(),
        findsNothing,
      );
      expect(tapped, isFalse);
    });

    testWidgets('tap calls onTap when visible', (tester) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: JumpToLatestButton(
                visible: true,
                onTap: () => tapped = true,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byType(JumpToLatestButton));
      expect(tapped, isTrue);
    });

    testWidgets('semantics label present for default and hasNewContent states', (tester) async {
      final handle = tester.ensureSemantics();

      // Default state: Jump to latest
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: JumpToLatestButton(
              visible: true,
              hasNewContent: false,
              onTap: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('Jump to latest message'), findsOneWidget);
      expect(find.text('Jump to latest'), findsOneWidget);

      // New content state: New messages
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: JumpToLatestButton(
              visible: true,
              hasNewContent: true,
              onTap: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('New messages, jump to latest'), findsOneWidget);
      expect(find.text('New messages'), findsOneWidget);

      handle.dispose();
    });

    testWidgets('reduced motion path (MediaQuery disableAnimations true) builds without animation error', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(disableAnimations: true),
            child: Scaffold(
              body: JumpToLatestButton(
                visible: true,
                onTap: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(JumpToLatestButton), findsOneWidget);

      // Toggle to false under reduced motion
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(disableAnimations: true),
            child: Scaffold(
              body: JumpToLatestButton(
                visible: false,
                onTap: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(
        find.byWidgetPredicate((w) => w is JumpToLatestButton).hitTestable(),
        findsNothing,
      );
    });

    testWidgets('touch target is at least 48x48', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: JumpToLatestButton(
                visible: true,
                onTap: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final size = tester.getSize(find.byType(JumpToLatestButton));
      expect(size.width, greaterThanOrEqualTo(48.0));
      expect(size.height, greaterThanOrEqualTo(48.0));
    });
  });
}
