import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_colors.dart';

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

enum Grade { fail, largeOrNonText, aa, aaa }

/// Normal-text grade: AAA ≥ 7, AA ≥ 4.5, large/non-text only ≥ 3, else fail.
Grade grade(double ratio) => ratio >= 7
    ? Grade.aaa
    : ratio >= 4.5
    ? Grade.aa
    : ratio >= 3
    ? Grade.largeOrNonText
    : Grade.fail;

String hex(Color c) =>
    '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

const white = Color(0xFFFFFFFF);

void main() {
  const l = KarmiColors.light;
  const d = KarmiColors.dark;

  group('§2.2 light tokens', () {
    final expected = <String, (Color, String)>{
      'background': (l.background, '#f4fbf5'),
      'foreground': (l.foreground, '#08160a'),
      'card': (l.card, '#ffffff'),
      'cardForeground': (l.cardForeground, '#08160a'),
      'primary': (l.primary, '#2c6d34'),
      'primaryForeground': (l.primaryForeground, '#f4fbf5'),
      'secondary': (l.secondary, '#86d0af'),
      'secondaryForeground': (l.secondaryForeground, '#08160a'),
      'accent': (l.accent, '#42a980'),
      'accentForeground': (l.accentForeground, '#08160a'),
      'muted': (l.muted, '#e6f2e8'),
      'mutedForeground': (l.mutedForeground, '#4b5e4e'),
      'border': (l.border, '#6f8a72'),
      'borderSubtle': (l.borderSubtle, '#d5e8d8'),
      'ring': (l.ring, '#2c6d34'),
      'destructive': (l.destructive, '#b42332'),
      'destructiveForeground': (l.destructiveForeground, '#ffffff'),
      'success (Design.md)': (l.success, '#146b43'),
      'warning (Design.md)': (l.warning, '#805000'),
    };
    for (final MapEntry(key: name, value: (color, want)) in expected.entries) {
      test(name, () {
        expect(hex(color), want);
        expect(color.a, 1.0, reason: '$name must be opaque');
      });
    }
  });

  group('§2.3 dark tokens', () {
    final expected = <String, (Color, String)>{
      'background': (d.background, '#08160a'),
      'foreground': (d.foreground, '#e8f5ea'),
      'card': (d.card, '#0d1f10'),
      'cardForeground': (d.cardForeground, '#e8f5ea'),
      'primary': (d.primary, '#86d0af'),
      'primaryForeground': (d.primaryForeground, '#08160a'),
      'secondary': (d.secondary, '#2c6d34'),
      'secondaryForeground': (d.secondaryForeground, '#e8f5ea'),
      'accent': (d.accent, '#42a980'),
      'accentForeground': (d.accentForeground, '#08160a'),
      'muted': (d.muted, '#1a2e1d'),
      'mutedForeground': (d.mutedForeground, '#a6b8a8'),
      'border': (d.border, '#5f7f63'),
      'borderSubtle (derived 129 26% 18%)': (d.borderSubtle, '#223a26'),
      'ring': (d.ring, '#86d0af'),
      'destructive': (d.destructive, '#ff9ca7'),
      'destructiveForeground': (d.destructiveForeground, '#08160a'),
      'success (Design.md)': (d.success, '#78ddaa'),
      'warning (Design.md)': (d.warning, '#ffd48a'),
    };
    for (final MapEntry(key: name, value: (color, want)) in expected.entries) {
      test(name, () {
        expect(hex(color), want);
        expect(color.a, 1.0, reason: '$name must be opaque');
      });
    }

    test('borderSubtle is a real, visible separator (not transparent)', () {
      expect(contrast(d.borderSubtle, d.background), greaterThan(1.3));
      expect(contrast(d.borderSubtle, d.card), greaterThan(1.3));
      // Decorative only, like light borderSubtle: stays below 3:1.
      expect(contrast(d.borderSubtle, d.background), lessThan(3));
    });
  });

  group('§2.4 WCAG ratios', () {
    // (label, fg, bg, published ratio, published grade)
    final pairs = <(String, Color, Color, double, Grade)>[
      // Brand pairs
      ('text on background', l.foreground, l.background, 17.68, Grade.aaa),
      ('text on card', l.foreground, l.card, 18.59, Grade.aaa),
      ('primary text on background', l.primary, l.background, 5.97, Grade.aa),
      ('primary on white', l.primary, white, 6.28, Grade.aa),
      ('background on primary', l.background, l.primary, 5.97, Grade.aa),
      ('white on primary', white, l.primary, 6.28, Grade.aa),
      ('text on primary', l.foreground, l.primary, 2.96, Grade.fail),
      ('white on accent', white, l.accent, 2.91, Grade.fail),
      ('text on accent', l.foreground, l.accent, 6.39, Grade.aa),
      ('accent text on background', l.accent, l.background, 2.77, Grade.fail),
      ('accent text on white', l.accent, white, 2.91, Grade.fail),
      ('text on secondary', l.foreground, l.secondary, 10.32, Grade.aaa),
      ('white on secondary', white, l.secondary, 1.80, Grade.fail),
      (
        'primary on secondary',
        l.primary,
        l.secondary,
        3.49,
        Grade.largeOrNonText,
      ),
      (
        'secondary text on background',
        l.secondary,
        l.background,
        1.71,
        Grade.fail,
      ),
      // Derived light pairs
      (
        'muted-fg on background',
        l.mutedForeground,
        l.background,
        6.63,
        Grade.aa,
      ),
      ('muted-fg on muted', l.mutedForeground, l.muted, 6.06, Grade.aa),
      ('text on muted', l.foreground, l.muted, 16.14, Grade.aaa),
      ('primary on muted', l.primary, l.muted, 5.45, Grade.aa),
      (
        'border on background',
        l.border,
        l.background,
        3.59,
        Grade.largeOrNonText,
      ),
      (
        'border-subtle on background',
        l.borderSubtle,
        l.background,
        1.22,
        Grade.fail,
      ),
      ('ring on background', l.ring, l.background, 5.97, Grade.aa),
      (
        'destructive text on background',
        l.destructive,
        l.background,
        6.19,
        Grade.aa,
      ),
      ('white on destructive', white, l.destructive, 6.51, Grade.aa),
      // Dark pairs
      ('dark fg on background', d.foreground, d.background, 16.54, Grade.aaa),
      ('dark fg on card', d.foreground, d.card, 15.30, Grade.aaa),
      ('dark fg on muted', d.foreground, d.muted, 12.86, Grade.aaa),
      ('dark primary text on card', d.primary, d.card, 9.55, Grade.aaa),
      ('dark primary text on muted', d.primary, d.muted, 8.02, Grade.aaa),
      (
        'dark primary-fg on primary',
        d.primaryForeground,
        d.primary,
        10.32,
        Grade.aaa,
      ),
      (
        'dark secondary-fg on secondary',
        d.secondaryForeground,
        d.secondary,
        5.59,
        Grade.aa,
      ),
      ('dark accent text on card', d.accent, d.card, 5.91, Grade.aa),
      (
        'dark accent-fg on accent',
        d.accentForeground,
        d.accent,
        6.39,
        Grade.aa,
      ),
      ('dark muted-fg on card', d.mutedForeground, d.card, 8.23, Grade.aaa),
      ('dark muted-fg on muted', d.mutedForeground, d.muted, 6.91, Grade.aa),
      ('dark border on card', d.border, d.card, 3.85, Grade.largeOrNonText),
      ('dark destructive text on card', d.destructive, d.card, 8.66, Grade.aaa),
      (
        'dark destructive-fg on destructive',
        d.destructiveForeground,
        d.destructive,
        9.35,
        Grade.aaa,
      ),
    ];

    for (final (label, fg, bg, published, want) in pairs) {
      test('$label: ${hex(fg)} on ${hex(bg)} = $published ($want)', () {
        final ratio = contrast(fg, bg);
        // Published ratios are rounded to 2 dp.
        expect(ratio, closeTo(published, 0.01));
        expect(grade(ratio), want);
      });
    }
  });

  group('StatusChip tone colours are text-grade on muted and card', () {
    for (final (name, c) in [('light', l), ('dark', d)]) {
      for (final tone in [
        c.success,
        c.primary,
        c.warning,
        c.destructive,
        c.mutedForeground,
      ]) {
        test('$name ${hex(tone)}', () {
          expect(contrast(tone, c.muted), greaterThanOrEqualTo(4.5));
          expect(contrast(tone, c.card), greaterThanOrEqualTo(4.5));
        });
      }
    }
  });
}
