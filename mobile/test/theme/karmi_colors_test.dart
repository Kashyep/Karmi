import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

/// WCAG 2.x relative luminance, computed independently of Flutter's
/// `computeLuminance` so the test pins the formula itself.
double _luminance(Color c) {
  double channel(double v) =>
      v <= 0.04045 ? v / 12.92 : math.pow((v + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}

double contrast(Color a, Color b) {
  final la = _luminance(a);
  final lb = _luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// Composites [fg] (with its alpha) over an opaque [bg].
Color over(Color fg, Color bg) => Color.alphaBlend(fg, bg);

String hex(Color c) =>
    '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

/// docs/design/karmi_tier_color_palettes.md, verbatim.
const palettes = <KarmiTier, Map<String, String>>{
  KarmiTier.ananta: {
    'accent': '#66c796',
    'base': '#1e422c',
    'light': '#f2f7f4',
    'dark': '#0b1a11',
    'text': '#050806',
  },
  KarmiTier.yanta: {
    'accent': '#00d4ff',
    'base': '#1a365d',
    'light': '#f4f6f9',
    'dark': '#0a111c',
    'text': '#8ba2c4',
  },
  KarmiTier.trika: {
    'accent': '#ff5722',
    'base': '#8c3b20',
    'light': '#fcf8f5',
    'dark': '#171210',
    'text': '#e0d4cd',
  },
  KarmiTier.parth: {
    'accent': '#d4af37',
    'secondary': '#9b4f96',
    'light': '#ffffff',
    'dark': '#000000',
    'text': '#1a1a1a',
  },
};

void main() {
  test('tier labels and ids (third tier is Trika)', () {
    expect(KarmiTier.values.map((t) => t.label), [
      'Ananta',
      'Yanta',
      'Trika',
      'Parth',
    ]);
    expect(KarmiTier.values.map((t) => t.id), [1, 2, 3, 4]);
    expect(KarmiTier.values.map((t) => t.planId), [
      'ananta',
      'yanta',
      'trika',
      'part',
    ]);
  });

  test('invalid tier ids are rejected', () {
    for (final bad in [0, 5, -1, '2', 2.0, null, true]) {
      expect(KarmiTier.fromId(bad), isNull, reason: '$bad');
    }
    expect(KarmiTier.fromId(3), KarmiTier.trika);
    expect(KarmiTier.fromPlanId('part'), KarmiTier.parth);
    expect(KarmiTier.fromPlanId('nope'), isNull);
  });

  for (final tier in KarmiTier.values) {
    final p = palettes[tier]!;
    group('${tier.label} palette is used unchanged', () {
      final light = KarmiColors.forTier(tier, Brightness.light);
      final dark = KarmiColors.forTier(tier, Brightness.dark);
      test('canvases', () {
        expect(hex(light.background), p['light']);
        expect(hex(dark.background), p['dark']);
      });
      test('accent is the primary fill in both modes', () {
        expect(hex(light.primary), p['accent']);
        expect(hex(dark.primary), p['accent']);
      });
      test('structural colour', () {
        if (tier == KarmiTier.parth) {
          expect(hex(dark.secondary), p['secondary']);
          expect(hex(light.accent), p['secondary']);
          expect(hex(light.foreground), p['text']);
        } else {
          expect(hex(light.header), p['base']);
          expect(hex(dark.header), p['base']);
        }
      });
    });
  }

  for (final tier in KarmiTier.values) {
    for (final brightness in Brightness.values) {
      final c = KarmiColors.forTier(tier, brightness);
      group('${tier.label} ${brightness.name} WCAG AA', () {
        for (final (name, surface) in [
          ('background', c.background),
          ('card', c.card),
          ('muted', c.muted),
        ]) {
          test('text on $name', () {
            for (final (ink, color) in [
              ('foreground', c.foreground),
              ('mutedForeground', c.mutedForeground),
              ('primaryText', c.primaryText),
              ('destructive', c.destructive),
              ('success', c.success),
              ('warning', c.warning),
            ]) {
              expect(
                contrast(color, surface),
                greaterThanOrEqualTo(4.5),
                reason: '$ink on $name',
              );
            }
          });
        }
        test('ink on fills', () {
          expect(
            contrast(c.primaryForeground, c.primary),
            greaterThanOrEqualTo(4.5),
          );
          expect(
            contrast(c.secondaryForeground, c.secondary),
            greaterThanOrEqualTo(4.5),
          );
          expect(
            contrast(c.accentForeground, c.accent),
            greaterThanOrEqualTo(4.5),
          );
          expect(
            contrast(c.destructiveForeground, c.destructive),
            greaterThanOrEqualTo(4.5),
          );
        });
        test('non-text: borders and focus ring ≥3:1', () {
          for (final s in [c.background, c.card]) {
            expect(contrast(c.border, s), greaterThanOrEqualTo(3));
            expect(contrast(c.ring, s), greaterThanOrEqualTo(3));
          }
        });
        test('text over glass stays ≥4.5:1 over worst-case backdrops', () {
          expect(
            c.glassBase.a,
            greaterThanOrEqualTo(brightness == Brightness.light ? 0.72 : 0.78),
          );
          for (final backdrop in [
            c.background,
            c.card,
            c.primary,
            c.secondary,
            c.foreground,
          ]) {
            final glass = over(c.glassBase, backdrop);
            expect(
              contrast(c.foreground, glass),
              greaterThanOrEqualTo(4.5),
              reason: 'over ${hex(backdrop)}',
            );
          }
        });
        test('disabled filled buttons stay readable', () {
          final theme = KarmiTheme.of(tier, brightness);
          final style = theme.filledButtonTheme.style!;
          final bg = style.backgroundColor!.resolve({WidgetState.disabled})!;
          final fg = style.foregroundColor!.resolve({WidgetState.disabled})!;
          expect(contrast(fg, bg), greaterThanOrEqualTo(4.5));
        });
        test('Material primary (text buttons, links) is text-grade', () {
          final scheme = KarmiTheme.of(tier, brightness).colorScheme;
          expect(contrast(scheme.primary, c.card), greaterThanOrEqualTo(4.5));
          expect(
            contrast(scheme.onPrimary, scheme.primary),
            greaterThanOrEqualTo(4.5),
          );
        });
      });
    }
  }

  test('theme lookup is cached (constant-time switch)', () {
    final a = KarmiTheme.of(KarmiTier.trika, Brightness.dark);
    final b = KarmiTheme.of(KarmiTier.trika, Brightness.dark);
    expect(identical(a, b), isTrue);
    expect(a.extension<KarmiTierTheme>()!.tier, KarmiTier.trika);
    expect(
      a.extension<KarmiColors>()!.background,
      KarmiColors.forTier(KarmiTier.trika, Brightness.dark).background,
    );
  });
}
