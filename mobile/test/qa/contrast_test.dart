import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/contrast.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/theme/karmi_tokens.dart';

void main() {
  group('WCAG contrast audit (theme/contrast.dart)', () {
    for (final tier in KarmiTier.values) {
      for (final brightness in Brightness.values) {
        final label = '${tier.name} ${brightness.name}';

        test('$label body text meets >= 4.5:1 ratio against background and card', () {
          final c = KarmiColors.forTier(tier, brightness);
          final textPairs = <String, (Color, Color)>{
            'foreground on background': (c.foreground, c.background),
            'foreground on card': (c.foreground, c.card),
            'cardForeground on card': (c.cardForeground, c.card),
            'mutedForeground on background': (c.mutedForeground, c.background),
            'mutedForeground on card': (c.mutedForeground, c.card),
            'primaryText on background': (c.primaryText, c.background),
            'primaryText on card': (c.primaryText, c.card),
          };

          for (final entry in textPairs.entries) {
            final ratio = contrastRatio(entry.value.$1, entry.value.$2);
            expect(
              ratio,
              greaterThanOrEqualTo(4.5),
              reason: '$label ${entry.key} had contrast ratio ${ratio.toStringAsFixed(2)} < 4.5',
            );
          }
        });

        test('$label UI boundary tokens meet >= 3.0:1 ratio against surface', () {
          final c = KarmiColors.forTier(tier, brightness);
          final uiPairs = <String, (Color, Color)>{
            'border on background': (c.border, c.background),
            'border on card': (c.border, c.card),
            'ring on background': (c.ring, c.background),
            'ring on card': (c.ring, c.card),
          };

          for (final entry in uiPairs.entries) {
            final ratio = contrastRatio(entry.value.$1, entry.value.$2);
            expect(
              ratio,
              greaterThanOrEqualTo(3.0),
              reason: '$label ${entry.key} had contrast ratio ${ratio.toStringAsFixed(2)} < 3.0',
            );
          }
        });
      }
    }

    test('KarmiTokens usage warning pill meets 4.5:1 text and 3:1 icon across both themes', () {
      for (final brightness in Brightness.values) {
        final fill = KarmiTokens.usageWarningFill(brightness);
        final fg = KarmiTokens.usageWarningForeground(brightness);
        final icon = KarmiTokens.usageWarningIcon(brightness);

        final fgRatio = contrastRatio(fg, fill);
        final iconRatio = contrastRatio(icon, fill);

        expect(
          fgRatio,
          greaterThanOrEqualTo(4.5),
          reason: '${brightness.name} usage warning text ratio ${fgRatio.toStringAsFixed(2)} < 4.5',
        );
        expect(
          iconRatio,
          greaterThanOrEqualTo(3.0),
          reason: '${brightness.name} usage warning icon ratio ${iconRatio.toStringAsFixed(2)} < 3.0',
        );
      }
    });
  });
}
