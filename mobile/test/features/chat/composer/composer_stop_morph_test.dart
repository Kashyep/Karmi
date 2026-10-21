import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

Widget _wrap(Widget child) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(
        body: Center(child: child),
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Composer stop morph and keys', () {
    testWidgets(
      'Case 5 (streaming): busy=true shows stop icon, stop semantics, and calls onStop on tap',
      (tester) async {
        var stopCount = 0;
        await tester.pumpWidget(
          _wrap(
            Composer(
              draftKey: 'test-stop-streaming',
              busy: true,
              onSubmit: (_) {},
              onStop: () => stopCount++,
              draftStore: MemoryDraftStore(),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Send button widget exists
        expect(
          find.byKey(const ValueKey('composer-send-button')),
          findsOneWidget,
        );

        // Stop icon is present while streaming
        expect(
          find.byKey(const ValueKey('composer-stop-icon')),
          findsOneWidget,
        );
        expect(find.byIcon(Icons.stop), findsOneWidget);

        // Send icon is absent while streaming
        expect(
          find.byKey(const ValueKey('composer-send-icon')),
          findsNothing,
        );

        // Semantics label is 'Stop generating'
        final stopSemantics = find.byWidgetPredicate(
          (w) =>
              w is Semantics &&
              w.properties.button == true &&
              w.properties.label == 'Stop generating',
        );
        expect(stopSemantics, findsOneWidget);

        // Tooltip is 'Stop generating'
        expect(find.byTooltip('Stop generating'), findsOneWidget);

        // Tapping the button calls onStop
        await tester.tap(find.byKey(const ValueKey('composer-send-button')));
        await tester.pump();
        expect(stopCount, equals(1));
      },
    );

    testWidgets(
      'Case 5 (not streaming): busy=false shows send icon, send semantics, and does not show stop icon',
      (tester) async {
        ComposerSubmit? submitted;
        await tester.pumpWidget(
          _wrap(
            Composer(
              draftKey: 'test-stop-idle',
              busy: false,
              onSubmit: (s) => submitted = s,
              onStop: () {},
              draftStore: MemoryDraftStore(),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Send button widget exists
        expect(
          find.byKey(const ValueKey('composer-send-button')),
          findsOneWidget,
        );

        // Stop icon is absent when not streaming
        expect(
          find.byKey(const ValueKey('composer-stop-icon')),
          findsNothing,
        );

        // Send icon is present
        expect(
          find.byKey(const ValueKey('composer-send-icon')),
          findsOneWidget,
        );
        expect(find.byIcon(Icons.arrow_upward), findsOneWidget);

        // Semantics label is 'Send message'
        final sendSemantics = find.byWidgetPredicate(
          (w) =>
              w is Semantics &&
              w.properties.button == true &&
              w.properties.label == 'Send message',
        );
        expect(sendSemantics, findsOneWidget);

        // Tooltip is 'Send message'
        expect(find.byTooltip('Send message'), findsOneWidget);

        // When text is entered, tapping sends
        await tester.enterText(find.byType(TextField), 'Hello world');
        await tester.pump();
        await tester.tap(find.byKey(const ValueKey('composer-send-button')));
        await tester.pump();

        expect(submitted, isNotNull);
        expect(submitted!.text, equals('Hello world'));
      },
    );

    testWidgets(
      'Composer exposes required ValueKeys: composer-surface, composer-attachment-tray, composer-send-button',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            Composer(
              draftKey: 'test-keys-presence',
              busy: false,
              onSubmit: (_) {},
              onStop: () {},
              draftStore: MemoryDraftStore(),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(
          find.byKey(const ValueKey('composer-surface')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('composer-attachment-tray')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('composer-send-button')),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'Morph transition: transitioning busy flag false -> true -> false toggles stop and send states',
      (tester) async {
        final draftStore = MemoryDraftStore();
        Widget buildTestHost(bool busy) {
          return _wrap(
            Composer(
              draftKey: 'test-morph-transition',
              busy: busy,
              onSubmit: (_) {},
              onStop: () {},
              draftStore: draftStore,
            ),
          );
        }

        // 1. Initial idle state (busy: false)
        await tester.pumpWidget(buildTestHost(false));
        await tester.pumpAndSettle();

        expect(find.byKey(const ValueKey('composer-send-icon')), findsOneWidget);
        expect(find.byKey(const ValueKey('composer-stop-icon')), findsNothing);

        // 2. Stream starts (busy: true)
        await tester.pumpWidget(buildTestHost(true));
        await tester.pumpAndSettle();

        expect(find.byKey(const ValueKey('composer-stop-icon')), findsOneWidget);
        expect(find.byKey(const ValueKey('composer-send-icon')), findsNothing);

        // 3. Stream completes (busy: false)
        await tester.pumpWidget(buildTestHost(false));
        await tester.pumpAndSettle();

        expect(find.byKey(const ValueKey('composer-send-icon')), findsOneWidget);
        expect(find.byKey(const ValueKey('composer-stop-icon')), findsNothing);
      },
    );
  });
}
