import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/widgets/karmi_logo.dart';

void main() {
  Widget host(Widget child) => MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, Brightness.dark),
    home: Scaffold(body: Center(child: child)),
  );

  testWidgets('draws a sized, painted mark', (tester) async {
    await tester.pumpWidget(host(const KarmiLogo(size: 32)));

    expect(find.byType(KarmiLogo), findsOneWidget);
    expect(tester.getSize(find.byType(KarmiLogo)), const Size(32, 32));
  });

  testWidgets('is announced as Karmi to screen readers', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(host(const KarmiLogo(size: 24)));

    expect(find.bySemanticsLabel('Karmi'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('can be hidden from the a11y tree when decorative', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      host(const KarmiLogo(size: 24, semanticLabel: null)),
    );

    expect(find.bySemanticsLabel('Karmi'), findsNothing);
    handle.dispose();
  });
}
