import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_colors.dart';

import '../support/harness.dart';

/// Device (Pixel 9a, hardware keyboard, 2026-09-26): Tab reached every control,
/// but the switch, list tiles and glass tabs showed no visible focus indicator,
/// and the theme segments shared one outline so the focused choice was unclear.
/// §8 requires a visible 2px `--ring` outline on the focused control.

/// Counts pixels within [rect] (logical px, DPR 1) close to the ring colour.
Future<int> ringPixels(WidgetTester tester, Rect rect) async {
  final ring = KarmiColors.light.ring;
  final image = await captureImage(tester.element(find.byType(MaterialApp)));
  final bytes = (await tester.runAsync(
    () => image.toByteData(format: ui.ImageByteFormat.rawRgba),
  ))!;
  int channel(double v) => (v * 255).round();
  final (rr, rg, rb) = (channel(ring.r), channel(ring.g), channel(ring.b));
  var count = 0;
  final r = rect
      .inflate(4)
      .intersect(
        Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
      );
  for (var y = r.top.floor(); y < r.bottom.floor(); y++) {
    for (var x = r.left.floor(); x < r.right.floor(); x++) {
      final i = (y * image.width + x) * 4;
      final d =
          (bytes.getUint8(i) - rr).abs() +
          (bytes.getUint8(i + 1) - rg).abs() +
          (bytes.getUint8(i + 2) - rb).abs();
      if (d < 40) count++;
    }
  }
  image.dispose();
  return count;
}

Future<void> tab(WidgetTester tester) async {
  await tester.sendKeyEvent(LogicalKeyboardKey.tab);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

/// Tabs until [label]'s control holds primary focus.
Future<void> focusByKeyboard(WidgetTester tester, Finder target) async {
  for (var i = 0; i < 40; i++) {
    final node = FocusManager.instance.primaryFocus;
    final focused = node is FocusScopeNode ? null : node?.context;
    if (focused != null &&
        find
            .descendant(of: find.byWidget(focused.widget), matching: target)
            .evaluate()
            .isNotEmpty) {
      return;
    }
    await tab(tester);
  }
  fail('keyboard focus never reached $target');
}

/// Pixels inside [rect] whose colour changed by ≥3:1 contrast between
/// [before] and [after] (a focus indicator must be a visible change).
Future<int> changedPixels(
  WidgetTester tester,
  Rect rect,
  Future<void> Function() change,
) async {
  Future<ByteData> grab() async {
    final image = await captureImage(tester.element(find.byType(MaterialApp)));
    final data = (await tester.runAsync(
      () => image.toByteData(format: ui.ImageByteFormat.rawRgba),
    ))!;
    width = image.width;
    image.dispose();
    return data;
  }

  final a = await grab();
  await change();
  final b = await grab();
  double lum(ByteData d, int i) {
    double ch(int v) {
      final c = v / 255;
      return c <= 0.04045
          ? c / 12.92
          : math.pow((c + 0.055) / 1.055, 2.4) * 1.0;
    }

    return 0.2126 * ch(d.getUint8(i)) +
        0.7152 * ch(d.getUint8(i + 1)) +
        0.0722 * ch(d.getUint8(i + 2));
  }

  var count = 0;
  for (var y = rect.top.floor(); y < rect.bottom.floor(); y++) {
    for (var x = rect.left.floor(); x < rect.right.floor(); x++) {
      final i = (y * width + x) * 4;
      final la = lum(a, i), lb = lum(b, i);
      final ratio = (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
      if (ratio >= 3) count++;
    }
  }
  return count;
}

int width = 0;

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  for (final label in ['Reduce transparency', 'Licences', 'Sign out']) {
    testWidgets('$label shows a ring when focused by keyboard', (tester) async {
      await pumpApp(tester);
      await openTab(tester, 'Settings');
      final text = find.text(label);
      final tile = find.ancestor(of: text, matching: find.byType(ListTile));
      final before = await ringPixels(tester, tester.getRect(tile.first));
      await focusByKeyboard(tester, text);
      final after = await ringPixels(tester, tester.getRect(tile.first));
      expect(
        after - before,
        greaterThan(200),
        reason: '$label: $before→$after',
      );
    });
  }

  testWidgets('the focused theme choice is distinguishable from the others', (
    tester,
  ) async {
    await pumpApp(tester);
    await openTab(tester, 'Settings');
    await focusByKeyboard(tester, find.text('Dark'));
    Future<int> at(String label) async {
      final button = find.ancestor(
        of: find.text(label),
        matching: find.byWidgetPredicate(
          (w) =>
              w is ButtonStyleButton ||
              w.runtimeType.toString().contains('Segment'),
        ),
      );
      return ringPixels(tester, tester.getRect(button.first));
    }

    final dark = await at('Dark');
    final light = await at('Light');
    final system = await at('System');
    expect(
      dark,
      greaterThan(light * 2 + 100),
      reason: 'dark=$dark light=$light',
    );
    expect(
      dark,
      greaterThan(system * 2 + 100),
      reason: 'dark=$dark system=$system',
    );
  });

  testWidgets('a glass tab shows a ring when focused by keyboard', (
    tester,
  ) async {
    await pumpApp(tester);
    final tabFinder = find.bySemanticsLabel('Memory tab');
    final rect = tester.getRect(tabFinder.first);
    final before = await ringPixels(tester, rect);
    await focusByKeyboard(tester, find.text('Memory'));
    final after = await ringPixels(tester, rect);
    expect(after - before, greaterThan(150), reason: '$before→$after');
  });

  // Device: Tab focused "Continue (development sign-in)" but the 2px ring was
  // drawn in --ring, which equals the --primary fill, so nothing changed.
  testWidgets('a focused filled button changes visibly (Welcome)', (
    tester,
  ) async {
    await pumpApp(tester, signedIn: false);
    final button = find.widgetWithText(
      FilledButton,
      'Continue (development sign-in)',
    );
    final changed = await changedPixels(
      tester,
      tester.getRect(button),
      () =>
          focusByKeyboard(tester, find.text('Continue (development sign-in)')),
    );
    expect(changed, greaterThan(400), reason: 'changed=$changed');
  });

  // Device: adb/hardware Tab moved focus but Android kept Flutter in touch
  // highlight mode, so a ring gated on traditional mode never appeared, while
  // Material buttons (which ring whenever focused) did.
  testWidgets('ring shows for keyboard focus even in touch highlight mode', (
    tester,
  ) async {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTouch;
    await pumpApp(tester);
    await openTab(tester, 'Settings');
    final text = find.text('Licences');
    final tile = find.ancestor(of: text, matching: find.byType(ListTile));
    await focusByKeyboard(tester, text);
    final count = await ringPixels(tester, tester.getRect(tile.first));
    expect(count, greaterThan(200), reason: 'ring pixels $count');
  });

  testWidgets('tapping a tab does not leave a focus ring behind', (
    tester,
  ) async {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTouch;
    await pumpApp(tester);
    final rect = tester.getRect(find.bySemanticsLabel('Memory tab').first);
    await openTab(tester, 'Memory');
    expect(await ringPixels(tester, rect), lessThan(50));
  });
}
