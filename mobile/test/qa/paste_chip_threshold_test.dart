import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:karmi_app/features/chat/composer/paste_chip.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class _InMemoryDraftStore implements DraftStore {
  final Map<String, String> _storage = {};

  @override
  Future<String?> load(String key) async => _storage[key];

  @override
  Future<void> save(String key, String text) async => _storage[key] = text;

  @override
  Future<void> clear(String key) async => _storage.remove(key);
}

Widget _buildComposerHost({
  required ValueChanged<ComposerSubmit> onSubmit,
  DraftStore? draftStore,
}) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(
        body: Composer(
          draftKey: 'qa-paste-threshold',
          busy: false,
          onSubmit: onSubmit,
          onStop: () {},
          draftStore: draftStore ?? _InMemoryDraftStore(),
        ),
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PasteChip threshold boundaries (2500 vs 2501 chars)', () {
    testWidgets(
      'pasting exactly 2500 chars is NOT chipped (remains raw text in input)',
      (tester) async {
        await tester.pumpWidget(_buildComposerHost(onSubmit: (_) {}));
        await tester.pumpAndSettle();

        final text2500 = 'A' * 2500;
        final textFieldFinder = find.byType(TextField);
        await tester.enterText(textFieldFinder, text2500);
        await tester.pump();

        expect(find.byType(PasteChip), findsNothing);
        final field = tester.widget<TextField>(textFieldFinder);
        expect(field.controller?.text, text2500);
      },
    );

    testWidgets(
      'pasting 2501 chars IS chipped into a PasteChip and cleared from input field',
      (tester) async {
        ComposerSubmit? submitted;
        await tester.pumpWidget(_buildComposerHost(onSubmit: (s) => submitted = s));
        await tester.pumpAndSettle();

        final text2501 = 'B' * 2501;
        final textFieldFinder = find.byType(TextField);
        await tester.enterText(textFieldFinder, text2501);
        await tester.pump();

        expect(find.byType(PasteChip), findsOneWidget);
        expect(find.text('Pasted text · 2501 chars'), findsOneWidget);

        // Input field itself is cleared of the long pasted text
        final field = tester.widget<TextField>(textFieldFinder);
        expect(field.controller?.text, isEmpty);

        // Submitting sends the complete 2501 chars
        await tester.tap(find.byTooltip('Send message'));
        await tester.pump();

        expect(submitted, isNotNull);
        expect(submitted!.text, text2501);
      },
    );

    testWidgets(
      'removing 2501-char paste chip deletes pasted content from submission',
      (tester) async {
        await tester.pumpWidget(_buildComposerHost(onSubmit: (_) {}));
        await tester.pumpAndSettle();

        final text2501 = 'C' * 2501;
        await tester.enterText(find.byType(TextField), text2501);
        await tester.pump();

        expect(find.byType(PasteChip), findsOneWidget);

        // Tap the remove icon button on PasteChip
        await tester.tap(find.byTooltip('Remove pasted text'));
        await tester.pump();

        expect(find.byType(PasteChip), findsNothing);

        // Send button should now be disabled since no text or chip remains
        final sendButton = tester.widget<IconButton>(
          find.widgetWithIcon(IconButton, Icons.arrow_upward),
        );
        expect(sendButton.onPressed, isNull);
      },
    );
  });
}
