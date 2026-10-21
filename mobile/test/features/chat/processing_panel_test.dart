import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/processing_panel.dart';

void main() {
  group('ProcessingPanel', () {
    testWidgets('renders nothing for idle phase', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: ProcessingPanel(phase: ChatRunPhase.idle)),
        ),
      );

      expect(find.text('Preparing'), findsNothing);
      expect(find.text('Writing'), findsNothing);
      expect(find.text('Still working…'), findsNothing);
      expect(find.byType(SizedBox), findsOneWidget);
    });

    testWidgets('renders nothing for finished phase', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: ProcessingPanel(phase: ChatRunPhase.finished)),
        ),
      );

      expect(find.text('Preparing'), findsNothing);
      expect(find.text('Writing'), findsNothing);
      expect(find.text('Still working…'), findsNothing);
      expect(find.byType(SizedBox), findsOneWidget);
    });

    testWidgets('renders nothing for error phase', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: ProcessingPanel(phase: ChatRunPhase.error)),
        ),
      );

      expect(find.text('Preparing'), findsNothing);
      expect(find.text('Writing'), findsNothing);
      expect(find.text('Still working…'), findsNothing);
      expect(find.byType(SizedBox), findsOneWidget);
    });

    testWidgets('sending phase displays "Preparing" with indicator', (
      tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: ProcessingPanel(phase: ChatRunPhase.sending)),
        ),
      );

      expect(find.text('Preparing'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      final semantics = tester.getSemantics(find.byType(ProcessingPanel));
      expect(semantics.label, contains('Preparing'));
      expect(
        tester
            .getSemantics(find.byType(ProcessingPanel))
            .getSemanticsData()
            .flagsCollection
            .isLiveRegion,
        isTrue,
      );
    });

    testWidgets('streaming phase displays "Writing" with indicator', (
      tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: ProcessingPanel(phase: ChatRunPhase.streaming)),
        ),
      );

      expect(find.text('Writing'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      final semantics = tester.getSemantics(find.byType(ProcessingPanel));
      expect(semantics.label, contains('Writing'));
    });

    testWidgets(
      'stalled phase displays "Still working…" and "Connection slow"',
      (tester) async {
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(body: ProcessingPanel(phase: ChatRunPhase.stalled)),
          ),
        );

        expect(find.text('Still working…'), findsOneWidget);
        expect(find.text('Connection slow'), findsOneWidget);
        expect(find.byType(CircularProgressIndicator), findsOneWidget);

        final semantics = tester.getSemantics(find.byType(ProcessingPanel));
        expect(semantics.label, contains('Still working…'));
      },
    );

    testWidgets(
      'reduced motion via disableAnimations renders without ticker errors and uses static icon',
      (tester) async {
        await tester.pumpWidget(
          const MediaQuery(
            data: MediaQueryData(disableAnimations: true),
            child: MaterialApp(
              home: Scaffold(
                body: ProcessingPanel(phase: ChatRunPhase.streaming),
              ),
            ),
          ),
        );

        // pumpAndSettle must succeed without timing out or throwing ticker errors
        await tester.pumpAndSettle();

        expect(find.text('Writing'), findsOneWidget);
        expect(find.byType(CircularProgressIndicator), findsNothing);
        expect(find.byIcon(Icons.more_horiz), findsOneWidget);
      },
    );
  });
}
