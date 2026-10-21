import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:karmi_app/features/chat/composer/paste_chip.dart';
import 'package:karmi_app/features/chat/composer/text_attachment.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class FakeDraftStore implements DraftStore {
  final Map<String, String> storage = {};
  int loadCalls = 0;
  int saveCalls = 0;
  int clearCalls = 0;

  @override
  Future<String?> load(String key) async {
    loadCalls++;
    return storage[key];
  }

  @override
  Future<void> save(String key, String text) async {
    saveCalls++;
    storage[key] = text;
  }

  @override
  Future<void> clear(String key) async {
    clearCalls++;
    storage.remove(key);
  }
}

Widget wrapWithTheme(Widget child) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(body: child),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Composer', () {
    testWidgets('Enter sends trimmed text, calls onSubmit once, clears field', (
      tester,
    ) async {
      ComposerSubmit? submitted;
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-1',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: FakeDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final textField = find.byType(TextField);
      await tester.enterText(textField, '   hello world   ');
      await tester.pump();

      // Press Enter key
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();

      expect(submitted, isNotNull);
      expect(submitted!.text, 'hello world');
      expect(submitted!.attachments, isEmpty);

      // Verify field cleared
      final fieldWidget = tester.widget<TextField>(textField);
      expect(fieldWidget.controller?.text, isEmpty);
    });

    testWidgets('Shift+Enter does not send message', (tester) async {
      ComposerSubmit? submitted;
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-2',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: FakeDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final textField = find.byType(TextField);
      await tester.enterText(textField, 'Line 1');
      await tester.pump();

      // Shift + Enter
      await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
      await tester.pump();

      expect(submitted, isNull);
    });

    testWidgets('busy shows Stop button and calls onStop when tapped', (
      tester,
    ) async {
      bool stopped = false;
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-busy',
            busy: true,
            onSubmit: (_) {},
            onStop: () => stopped = true,
            draftStore: FakeDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final stopButton = find.byTooltip('Stop generating');
      expect(stopButton, findsOneWidget);
      expect(find.byIcon(Icons.stop), findsOneWidget);

      await tester.tap(stopButton);
      await tester.pump();

      expect(stopped, isTrue);
    });

    testWidgets('send button disabled when empty, enabled when text present', (
      tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-send-button',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            draftStore: FakeDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final sendBtnFinder = find.widgetWithIcon(IconButton, Icons.arrow_upward);
      expect(sendBtnFinder, findsOneWidget);

      IconButton button = tester.widget<IconButton>(sendBtnFinder);
      expect(button.onPressed, isNull);

      await tester.enterText(find.byType(TextField), 'valid message');
      await tester.pump();

      button = tester.widget<IconButton>(sendBtnFinder);
      expect(button.onPressed, isNotNull);
    });

    testWidgets('paste >= 2500 chars becomes chip, 2499 does not', (
      tester,
    ) async {
      ComposerSubmit? submitted;
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-paste',
            busy: false,
            onSubmit: (s) => submitted = s,
            onStop: () {},
            draftStore: FakeDraftStore(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Enter 2499 chars -> should NOT create PasteChip
      final text2499 = 'A' * 2499;
      await tester.enterText(find.byType(TextField), text2499);
      await tester.pump();

      expect(find.byType(PasteChip), findsNothing);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller?.text,
        text2499,
      );

      // Clear field
      await tester.enterText(find.byType(TextField), '');
      await tester.pump();

      // 2. Paste 2500 chars -> should collapse into PasteChip
      final text2500 = 'B' * 2500;
      await tester.enterText(find.byType(TextField), text2500);
      await tester.pump();

      expect(find.byType(PasteChip), findsOneWidget);
      expect(find.text('Pasted text · 2500 chars'), findsOneWidget);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller?.text,
        isEmpty,
      );

      // Submit and verify pasted text is included in submission
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();

      expect(submitted, isNotNull);
      expect(submitted!.text, text2500);
    });

    testWidgets('4th file rejected with message', (tester) async {
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-att-count',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            draftStore: FakeDraftStore(),
            onPickAttachments: () async => [
              const TextAttachment(name: '1.txt', content: 'one'),
              const TextAttachment(name: '2.txt', content: 'two'),
              const TextAttachment(name: '3.txt', content: 'three'),
              const TextAttachment(name: '4.txt', content: 'four'),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Attach files'));
      await tester.pumpAndSettle();

      expect(find.text('Maximum 3 files allowed.'), findsOneWidget);
    });

    testWidgets('40,001-char file rejected with message', (tester) async {
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-att-large',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            draftStore: FakeDraftStore(),
            onPickAttachments: () async => [
              TextAttachment(name: 'huge.txt', content: 'z' * 40001),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Attach files'));
      await tester.pumpAndSettle();

      expect(find.textContaining('40,000 character limit'), findsOneWidget);
    });

    testWidgets('total 60,001 chars rejected with message', (tester) async {
      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'test-att-total',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            draftStore: FakeDraftStore(),
            onPickAttachments: () async => [
              TextAttachment(name: 'a.txt', content: 'x' * 30000),
              TextAttachment(name: 'b.txt', content: 'y' * 30001),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Attach files'));
      await tester.pumpAndSettle();

      expect(find.textContaining('60,000 character limit'), findsOneWidget);
    });

    testWidgets('draft load, debounced save, and clear with fake DraftStore', (
      tester,
    ) async {
      final fakeStore = FakeDraftStore()
        ..storage['draft-key-1'] = 'initial draft';

      await tester.pumpWidget(
        wrapWithTheme(
          Composer(
            draftKey: 'draft-key-1',
            busy: false,
            onSubmit: (_) {},
            onStop: () {},
            draftStore: fakeStore,
          ),
        ),
      );
      // Wait for async loadDraft to complete
      await tester.pumpAndSettle();

      expect(
        tester.widget<TextField>(find.byType(TextField)).controller?.text,
        'initial draft',
      );
      expect(fakeStore.loadCalls, 1);

      // Edit text to trigger debounced save
      await tester.enterText(find.byType(TextField), 'updated draft');
      await tester.pump();

      // Before 300ms debounce: save should not have fired yet
      expect(fakeStore.storage['draft-key-1'], 'initial draft');

      // Advance clock past 300ms
      await tester.pump(const Duration(milliseconds: 350));
      expect(fakeStore.storage['draft-key-1'], 'updated draft');

      // Submit clears draft
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();

      expect(fakeStore.clearCalls, 1);
      expect(fakeStore.storage['draft-key-1'], isNull);
    });

    testWidgets(
      'switching draftKey in didUpdateWidget saves old draft and loads new one',
      (tester) async {
        final fakeStore = FakeDraftStore()
          ..storage['chat-a'] = 'chat a draft'
          ..storage['chat-b'] = 'chat b draft';

        await tester.pumpWidget(
          wrapWithTheme(
            Composer(
              draftKey: 'chat-a',
              busy: false,
              onSubmit: (_) {},
              onStop: () {},
              draftStore: fakeStore,
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(
          tester.widget<TextField>(find.byType(TextField)).controller?.text,
          'chat a draft',
        );

        // Modify chat-a text
        await tester.enterText(find.byType(TextField), 'chat a modified');
        await tester.pump();

        // Switch to chat-b
        await tester.pumpWidget(
          wrapWithTheme(
            Composer(
              draftKey: 'chat-b',
              busy: false,
              onSubmit: (_) {},
              onStop: () {},
              draftStore: fakeStore,
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Old draft saved and new draft loaded
        expect(fakeStore.storage['chat-a'], 'chat a modified');
        expect(
          tester.widget<TextField>(find.byType(TextField)).controller?.text,
          'chat b draft',
        );
      },
    );
  });
}
