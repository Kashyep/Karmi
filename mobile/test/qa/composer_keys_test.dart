import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class _KeyDraftStore implements DraftStore {
  @override
  Future<String?> load(String key) async => null;
  @override
  Future<void> save(String key, String text) async {}
  @override
  Future<void> clear(String key) async {}
}

Widget _wrap(Widget child) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(body: child),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Composer keyboard handling', () {
    testWidgets(
      'Enter sends trimmed text, clears input, and notifies onSubmit',
      (tester) async {
        ComposerSubmit? submitted;
        await tester.pumpWidget(
          _wrap(
            Composer(
              draftKey: 'test-enter',
              busy: false,
              onSubmit: (s) => submitted = s,
              onStop: () {},
              draftStore: _KeyDraftStore(),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final textField = find.byType(TextField);
        await tester.enterText(textField, 'Hello from Enter');
        await tester.pump();

        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pump();

        expect(submitted, isNotNull);
        expect(submitted!.text, 'Hello from Enter');
        final field = tester.widget<TextField>(textField);
        expect(field.controller?.text, isEmpty);
      },
    );

    testWidgets('Shift+Enter inserts newline and does NOT send', (
      tester,
    ) async {
      ComposerSubmit? submitted;
      await tester.pumpWidget(
        _wrap(
          Composer(
            draftKey: 'test-shift-enter',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: _KeyDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final textField = find.byType(TextField);
      await tester.enterText(textField, 'Line 1');
      await tester.pump();

      await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
      await tester.pump();

      expect(submitted, isNull);
    });

    testWidgets('IME composing does not send on Enter', (tester) async {
      ComposerSubmit? submitted;
      await tester.pumpWidget(
        _wrap(
          Composer(
            draftKey: 'test-ime',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: _KeyDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final textField = find.byType(TextField);
      await tester.tap(textField);
      await tester.pump();

      // Simulate active IME composing candidate
      final controller = tester.widget<TextField>(textField).controller!;
      controller.value = const TextEditingValue(
        text: 'nihon',
        selection: TextSelection.collapsed(offset: 5),
        composing: TextRange(start: 0, end: 5),
      );
      await tester.pump();

      // Press Enter during IME composition (confirm candidate)
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();

      // Must not send while composing
      expect(submitted, isNull);
    });

    testWidgets(
      'IME composing transitions: valid range blocks Enter, invalid range allows Enter',
      (tester) async {
        ComposerSubmit? submitted;
        await tester.pumpWidget(
          _wrap(
            Composer(
              draftKey: 'test-ime-transition',
              busy: false,
              onSubmit: (s) => submitted = s,
              onStop: () {},
              draftStore: _KeyDraftStore(),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final textField = find.byType(TextField);
        await tester.tap(textField);
        await tester.pump();

        final controller = tester.widget<TextField>(textField).controller!;
        // 1. While composing is valid, Enter must not submit
        controller.value = const TextEditingValue(
          text: 'konnichiwa',
          selection: TextSelection.collapsed(offset: 10),
          composing: TextRange(start: 0, end: 10),
        );
        await tester.pump();

        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pump();
        expect(submitted, isNull);

        // 2. Once composing ends (invalid composing range), Enter must submit
        controller.value = const TextEditingValue(
          text: 'konnichiwa',
          selection: TextSelection.collapsed(offset: 10),
          composing: TextRange.empty,
        );
        await tester.pump();

        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pump();
        expect(submitted, isNotNull);
        expect(submitted!.text, 'konnichiwa');
      },
    );
  });
}
