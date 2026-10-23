import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/contrast.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/theme/karmi_tokens.dart';

void main() {
  group('tier colour contrast', () {
    for (final tier in KarmiTier.values) {
      for (final brightness in Brightness.values) {
        final name = '${tier.name} ${brightness.name}';

        test('$name text tokens meet 4.5:1 (WCAG AA)', () {
          final c = KarmiColors.forTier(tier, brightness);
          final pairs = <String, (Color, Color)>{
            'foreground/background': (c.foreground, c.background),
            'cardForeground/card': (c.cardForeground, c.card),
            'mutedForeground/background': (c.mutedForeground, c.background),
            'mutedForeground/card': (c.mutedForeground, c.card),
            'primaryText/background': (c.primaryText, c.background),
            'primaryText/card': (c.primaryText, c.card),
          };
          for (final entry in pairs.entries) {
            final ratio = contrastRatio(entry.value.$1, entry.value.$2);
            expect(
              ratio,
              greaterThanOrEqualTo(4.5),
              reason: '$name ${entry.key} = ${ratio.toStringAsFixed(2)}',
            );
          }
        });

        test('$name UI boundary tokens meet 3:1 against background', () {
          final c = KarmiColors.forTier(tier, brightness);
          final pairs = <String, (Color, Color)>{
            'border/background': (c.border, c.background),
            'ring/background': (c.ring, c.background),
          };
          for (final entry in pairs.entries) {
            final ratio = contrastRatio(entry.value.$1, entry.value.$2);
            expect(
              ratio,
              greaterThanOrEqualTo(3.0),
              reason: '$name ${entry.key} = ${ratio.toStringAsFixed(2)}',
            );
          }
        });
      }
    }
  });

  group('usage warning pill colours', () {
    for (final brightness in Brightness.values) {
      test('${brightness.name} text ≥4.5:1 and icon ≥3:1 on fill', () {
        final fill = KarmiTokens.usageWarningFill(brightness);
        expect(
          contrastRatio(KarmiTokens.usageWarningForeground(brightness), fill),
          greaterThanOrEqualTo(4.5),
        );
        expect(
          contrastRatio(KarmiTokens.usageWarningIcon(brightness), fill),
          greaterThanOrEqualTo(3.0),
        );
      });
    }
  });

  group('isUsageWarning', () {
    test('threshold boundaries', () {
      expect(KarmiTokens.isUsageWarning(0.79), isFalse);
      expect(KarmiTokens.isUsageWarning(0.8), isTrue);
      expect(KarmiTokens.isUsageWarning(1.0), isTrue);
      expect(KarmiTokens.isUsageWarning(0), isFalse);
    });

    test('NaN is never a warning', () {
      expect(KarmiTokens.isUsageWarning(double.nan), isFalse);
    });
  });

  group('motion', () {
    testWidgets('disableAnimations yields zero duration', (tester) async {
      late Duration result;
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(disableAnimations: true),
            child: Builder(
              builder: (context) {
                result = KarmiTokens.motion(context, KarmiTokens.standard);
                return const SizedBox();
              },
            ),
          ),
        ),
      );
      expect(result, Duration.zero);
    });

    testWidgets('normal motion keeps 180ms', (tester) async {
      late Duration result;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              result = KarmiTokens.motion(context, KarmiTokens.standard);
              return const SizedBox();
            },
          ),
        ),
      );
      expect(result, const Duration(milliseconds: 180));
    });

    testWidgets('KarmiAccessibility(reduceMotion: true) yields zero', (
      tester,
    ) async {
      late Duration result;
      await tester.pumpWidget(
        MaterialApp(
          home: KarmiAccessibility(
            reduceTransparency: false,
            reduceMotion: true,
            child: Builder(
              builder: (context) {
                result = KarmiTokens.motion(context, KarmiTokens.standard);
                return const SizedBox();
              },
            ),
          ),
        ),
      );
      expect(result, Duration.zero);
    });
  });

  group('specular border', () {
    test('dark alpha is stronger than light', () {
      expect(KarmiTokens.specularBorderAlpha(Brightness.dark), 0.18);
      expect(KarmiTokens.specularBorderAlpha(Brightness.light), 0.10);
      expect(
        KarmiTokens.specularBorderAlpha(Brightness.dark),
        greaterThan(KarmiTokens.specularBorderAlpha(Brightness.light)),
      );
    });
  });
}
