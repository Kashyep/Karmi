import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_glass.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

/// Failures observed on the Pixel 9a (release gate, 2026-09-26), reproduced
/// here before they were fixed.

double _contrast(Color a, Color b) {
  double lum(Color c) {
    double ch(double v) => v <= 0.04045
        ? v / 12.92
        : math.pow((v + 0.055) / 1.055, 2.4).toDouble();
    return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
  }

  final x = lum(a), y = lum(b);
  return (math.max(x, y) + 0.05) / (math.min(x, y) + 0.05);
}

Future<void> _type(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
}

Future<void> _send(WidgetTester tester, String text) async {
  await _type(tester, text);
  await tester.tap(find.byTooltip('Send message'));
  await settle(tester);
}

void main() {
  // Device: the enabled send icon was invisible in the glass shell. GlassScaffold
  // installs a Cupertino IconTheme (primary colour) that IconButton adopts as its
  // foreground, so the filled button drew a primary icon on a primary fill.
  for (final rt in [false, true]) {
    testWidgets('enabled send icon contrasts with its fill '
        '(${rt ? 'opaque' : 'glass'} shell)', (tester) async {
      await pumpApp(tester, env: Env(reduceTransparency: rt));
      await _type(tester, 'hi');
      final icon = tester.widget<RichText>(
        find.descendant(
          of: find.byIcon(Icons.send),
          matching: find.byType(RichText),
        ),
      );
      final ratio = _contrast(
        icon.text.style!.color!,
        KarmiColors.light.primary,
      );
      expect(
        ratio,
        greaterThanOrEqualTo(3),
        reason: 'non-text contrast $ratio',
      );
    });
  }

  // Device: the glass app bar had no platter (transparent background), so the
  // title and the status bar sat directly on whatever scrolled underneath, e.g.
  // a primary-filled user bubble (2.96:1). In widget tests the scroll-edge
  // effect falls back to an opaque gradient, so the pixels cannot show this;
  // the bar's tint is asserted against the §5.1 legibility floor instead.
  for (final brightness in Brightness.values) {
    testWidgets('glass app bar has a tint platter at the legibility floor '
        '(${brightness.name})', (tester) async {
      await pumpApp(tester, env: Env(brightness: brightness));
      final bar = tester.widget<GlassAppBar>(find.byType(GlassAppBar));
      final (card, floor) = brightness == Brightness.light
          ? (KarmiColors.light.card, KarmiGlass.lightTintAlpha)
          : (KarmiColors.dark.card, KarmiGlass.darkTintAlpha);
      expect(bar.backgroundColor.a, greaterThanOrEqualTo(floor));
      expect(bar.backgroundColor.withValues(alpha: 1), card);
    });
  }

  // Device: switching reduce transparency (or system high contrast) rebuilt the
  // shell with a different scaffold and discarded the chat transcript.
  testWidgets('toggling reduce transparency keeps the transcript and tab', (
    tester,
  ) async {
    final app = await pumpApp(
      tester,
      backend: FakeBackend.healthy()
        ..on(
          'POST',
          '/v1/messages',
          (_) => jsonResponse(messageJson('ACCEPT', response: 'Kept reply')),
        ),
    );
    await _send(tester, 'Keep me');
    expect(find.text('Kept reply'), findsOneWidget);

    await app.settings.setReduceTransparency(true);
    await settle(tester);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('Keep me'), findsOneWidget);
    expect(find.text('Kept reply'), findsOneWidget);

    await app.settings.setReduceTransparency(false);
    await settle(tester);
    expect(find.byType(GlassTabBar), findsOneWidget);
    expect(find.text('Kept reply'), findsOneWidget);
  });

  // Device (TalkBack): the Licences tile merged into its Card's semantics node,
  // so its focus rectangle covered the whole card and TalkBack read "Licences"
  // before "Reduce transparency".
  testWidgets('settings card exposes each control as its own node in order', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    await openTab(tester, 'Settings');
    final licences = tester.getSemantics(
      find.bySemanticsLabel(RegExp('^Licences')),
    );
    final toggle = tester.getSemantics(
      find.bySemanticsLabel(RegExp('^Reduce transparency')),
    );
    final licencesRect = tester.getRect(find.text('Licences'));
    final toggleRect = tester.getRect(find.text('Reduce transparency'));
    Rect global(SemanticsNode node) {
      var rect = node.rect;
      for (SemanticsNode? n = node; n != null; n = n.parent) {
        if (n.transform != null) {
          rect = MatrixUtils.transformRect(n.transform!, rect);
        }
      }
      return rect;
    }

    // The Licences node must not swallow the toggle row above it.
    expect(global(licences).contains(toggleRect.center), isFalse);
    expect(global(licences).contains(licencesRect.center), isTrue);
    expect(global(toggle).top, lessThan(global(licences).top));
    handle.dispose();
  });

  // Device (TalkBack / uiautomator): with the glass overflow menu open, its
  // items were missing from the accessibility tree, so screen-reader users
  // could not reach Plans or Licences.
  testWidgets('overflow menu items are reachable by screen readers', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    await tester.tap(find.byTooltip('More options'));
    await settle(tester);
    for (final label in ['Plans', 'Licences']) {
      // Search the real semantics tree (what TalkBack sees), not widgets.
      // Offstage tabs (e.g. the Usage "Plans" heading) are not in the tree.
      final nodes = find.semantics
          .byLabel(label)
          .evaluate()
          .where((n) => n.getSemanticsData().hasAction(SemanticsAction.tap));
      expect(nodes, isNotEmpty, reason: '$label not in the semantics tree');
    }
    await tester.tap(find.text('Plans').last);
    await settle(tester);
    expect(
      find.text(
        'Compare plans. Purchases are unavailable in this build, '
        'so your plan cannot be changed here.',
      ),
      findsOneWidget,
    );
    handle.dispose();
  });

  // Device (uiautomator): after replacing the SegmentedButton with separate
  // buttons, the current theme choice no longer reported "selected".
  testWidgets('theme choices expose selected state to screen readers', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    await openTab(tester, 'Settings');
    bool selected(String label) => find.semantics
        .byLabel(label)
        .evaluate()
        .any(
          (n) =>
              n.getSemanticsData().flagsCollection.isSelected ==
              ui.Tristate.isTrue,
        );
    expect(selected('Light'), isTrue);
    expect(selected('Dark'), isFalse);
    expect(selected('System'), isFalse);
    handle.dispose();
  });
}
