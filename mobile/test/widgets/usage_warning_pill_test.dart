import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/widgets/usage_warning_pill.dart';

Future<void> _pump(WidgetTester tester, double fraction, Brightness b) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, b),
      home: Scaffold(body: UsageWarningPill(fraction: fraction)),
    ),
  );
}

void main() {
  for (final brightness in Brightness.values) {
    group('UsageWarningPill (${brightness.name})', () {
      testWidgets('hidden below threshold', (tester) async {
        await _pump(tester, 0.79, brightness);
        expect(find.byKey(const ValueKey('usage-warning-pill')), findsNothing);
        expect(
          find.byKey(const ValueKey('usage-warning-pill-hidden')),
          findsOneWidget,
        );
        expect(find.text('Near limit'), findsNothing);
      });

      testWidgets('shows "Near limit" at 0.8 with semantics label', (
        tester,
      ) async {
        final handle = tester.ensureSemantics();
        await _pump(tester, 0.8, brightness);
        expect(
          find.byKey(const ValueKey('usage-warning-pill')),
          findsOneWidget,
        );
        expect(find.text('Near limit'), findsOneWidget);
        expect(find.bySemanticsLabel('Near limit'), findsOneWidget);
        handle.dispose();
      });

      testWidgets('shows "Allowance reached" at 1.0', (tester) async {
        final handle = tester.ensureSemantics();
        await _pump(tester, 1.0, brightness);
        expect(
          find.byKey(const ValueKey('usage-warning-pill')),
          findsOneWidget,
        );
        expect(find.text('Allowance reached'), findsOneWidget);
        expect(find.bySemanticsLabel('Allowance reached'), findsOneWidget);
        handle.dispose();
      });
    });
  }
}
