import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import '../support/harness.dart';

class _KeyDraftStore implements DraftStore {
  @override
  Future<String?> load(String key) async => null;
  @override
  Future<void> save(String key, String text) async {}
  @override
  Future<void> clear(String key) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('A11y Keyboard Tests', () {
    testWidgets('Composer: Enter sends trimmed text, clears input, and notifies onSubmit', (tester) async {
      ComposerSubmit? submitted;
      await pumpHost(
        tester,
        Center(
          child: Composer(
            draftKey: 'test-enter',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: _KeyDraftStore(),
          ),
        ),
      );

      final textField = find.byType(TextField);
      await tester.enterText(textField, 'Hello from Enter');
      await tester.pump();

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();

      expect(submitted, isNotNull);
      expect(submitted!.text, 'Hello from Enter');
      final field = tester.widget<TextField>(textField);
      expect(field.controller?.text, isEmpty);
    });

    testWidgets('Composer: Shift+Enter inserts newline and does NOT send', (tester) async {
      ComposerSubmit? submitted;
      await pumpHost(
        tester,
        Center(
          child: Composer(
            draftKey: 'test-shift-enter',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: _KeyDraftStore(),
          ),
        ),
      );

      final textField = find.byType(TextField);
      await tester.enterText(textField, 'Line 1');
      await tester.pump();

      await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
      await tester.pump();

      expect(submitted, isNull);
    });

    testWidgets('Tab traversal across composer -> attach -> send is in order', (tester) async {
      await pumpHost(
        tester,
        Center(
          child: Composer(
            draftKey: 'test-tab',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            onPickAttachments: () => null,
            draftStore: _KeyDraftStore(),
          ),
        ),
      );

      final textField = find.byType(TextField);
      await tester.tap(textField);
      await tester.pump();
      // Send is disabled (and unfocusable) on an empty draft.
      await tester.enterText(textField, 'draft');
      await tester.pump();

      // Composer (TextField) currently has focus
      final textNode = FocusManager.instance.primaryFocus;
      expect(textNode, isNotNull);

      // Press Tab -> focus moves to Attach button
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
      final attachFinder = find.byTooltip('Attach files');
      expect(attachFinder, findsOneWidget);
      final attachNode = FocusManager.instance.primaryFocus;
      expect(attachNode, isNotNull);
      expect(attachNode, isNot(equals(textNode)));
      expect(
        attachNode!.context!.findAncestorWidgetOfExactType<IconButton>()?.tooltip == 'Attach files',
        isTrue,
        reason: 'Focus should be on Attach button',
      );

      // Press Tab -> focus moves to Send button
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
      final sendFinder = find.byTooltip('Send message');
      expect(sendFinder, findsOneWidget);
      final sendNode = FocusManager.instance.primaryFocus;
      expect(sendNode, isNotNull);
      expect(sendNode, isNot(equals(attachNode)));
      expect(
        sendNode!.context!.findAncestorWidgetOfExactType<IconButton>()?.tooltip == 'Send message',
        isTrue,
        reason: 'Focus should be on Send button',
      );
    });

    testWidgets('Esc key focus behavior (no Esc dismiss in lib)', (tester) async {
      await pumpHost(
        tester,
        Center(
          child: Composer(
            draftKey: 'test-esc',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            draftStore: _KeyDraftStore(),
          ),
        ),
      );

      final textField = find.byType(TextField);
      await tester.tap(textField);
      await tester.pump();

      final nodeBefore = FocusManager.instance.primaryFocus;
      expect(nodeBefore, isNotNull);

      // App has no Esc dismiss handling; pressing Esc retains or does not crash focus
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pump();

      final nodeAfter = FocusManager.instance.primaryFocus;
      expect(nodeAfter, isNotNull);
    });
  });
}
