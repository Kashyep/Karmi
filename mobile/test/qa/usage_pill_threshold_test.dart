import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/widgets/usage_warning_pill.dart';

Widget _buildHost(double fraction, Brightness brightness) {
  return MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, brightness),
    home: Scaffold(
      body: Center(child: UsageWarningPill(fraction: fraction)),
    ),
  );
}

void main() {
  group('UsageWarningPill threshold behavior (0.8 vs 0.79)', () {
    for (final brightness in Brightness.values) {
      testWidgets('at 0.79 usage is hidden (${brightness.name})', (
        tester,
      ) async {
        await tester.pumpWidget(_buildHost(0.79, brightness));
        await tester.pumpAndSettle();

        expect(find.byKey(const ValueKey('usage-warning-pill')), findsNothing);
        expect(
          find.byKey(const ValueKey('usage-warning-pill-hidden')),
          findsOneWidget,
        );
        expect(find.text('Near limit'), findsNothing);
      });

      testWidgets('at 0.80 usage warning pill shows (${brightness.name})', (
        tester,
      ) async {
        final handle = tester.ensureSemantics();
        await tester.pumpWidget(_buildHost(0.80, brightness));
        await tester.pumpAndSettle();

        expect(
          find.byKey(const ValueKey('usage-warning-pill')),
          findsOneWidget,
        );
        expect(find.text('Near limit'), findsOneWidget);
        expect(find.bySemanticsLabel('Near limit'), findsOneWidget);
        expect(find.byIcon(Icons.warning_amber), findsOneWidget);
        handle.dispose();
      });

      testWidgets(
        'precision boundaries: 0.7999 hidden, 0.8000 shown (${brightness.name})',
        (tester) async {
          await tester.pumpWidget(_buildHost(0.7999, brightness));
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('usage-warning-pill')),
            findsNothing,
          );

          await tester.pumpWidget(_buildHost(0.8000, brightness));
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('usage-warning-pill')),
            findsOneWidget,
          );
        },
      );
    }
  });
}
