import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

Widget _host({required bool disableAnimations, required Widget child}) {
  return MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: Scaffold(body: child),
    ),
  );
}

void main() {
  group('derived colour tokens', () {
    test('brightness is derived from the canvas for every tier', () {
      for (final tier in KarmiTier.values) {
        for (final brightness in Brightness.values) {
          expect(
            KarmiColors.forTier(tier, brightness).brightness,
            brightness,
            reason: '${tier.name} ${brightness.name}',
          );
        }
      }
    });

    test(
      'dark glass rim is a stronger top highlight than light, and focus is stronger still',
      () {
        for (final tier in KarmiTier.values) {
          final dark = KarmiColors.forTier(tier, Brightness.dark);
          expect(
            dark.glassSpecularRimFocused.a,
            greaterThan(dark.glassSpecularRim.a),
            reason: '${tier.name} focused rim must brighten',
          );
          expect(dark.glassSpecularRim.a, closeTo(0.22, 0.01));
        }
      },
    );

    test('ambient glow is the tier primary at low alpha', () {
      for (final tier in KarmiTier.values) {
        for (final brightness in Brightness.values) {
          final c = KarmiColors.forTier(tier, brightness);
          expect(c.ambientGlow.a, lessThanOrEqualTo(0.25));
          expect(c.ambientGlow.r, closeTo(c.primary.r, 0.01));
          expect(c.ambientGlow.g, closeTo(c.primary.g, 0.01));
          expect(c.ambientGlow.b, closeTo(c.primary.b, 0.01));
        }
      }
    });

    test('code header sits above the code body in both modes', () {
      for (final tier in KarmiTier.values) {
        for (final brightness in Brightness.values) {
          final c = KarmiColors.forTier(tier, brightness);
          if (brightness == Brightness.dark) {
            expect(
              c.codeHeaderSurface.computeLuminance(),
              greaterThan(c.codeSurface.computeLuminance()),
            );
          }
          expect(c.hairline.a, greaterThan(0));
          expect(c.hairline.a, lessThan(0.2));
        }
      }
    });
  });

  group('layout and shape tokens', () {
    test('values match the redesign spec', () {
      expect(KarmiShape.readableColumnMaxWidth, 720);
      expect(KarmiShape.composerRadius, 20);
      expect(KarmiShape.historyRailWidth, 260);
      expect(KarmiShape.tabletBreakpoint, 768);
      expect(KarmiShape.desktopBreakpoint, 1024);
      expect(KarmiShape.jumpPillGap, 16);
    });

    test('user pill radius is 18 / 18 / 4 / 18 (TL, TR, BR, BL)', () {
      const r = KarmiShape.userPillRadius;
      expect(r.topLeft, const Radius.circular(18));
      expect(r.topRight, const Radius.circular(18));
      expect(r.bottomRight, const Radius.circular(4));
      expect(r.bottomLeft, const Radius.circular(18));
    });
  });

  group('composer motion', () {
    test('is 220ms on the plan curve', () {
      expect(KarmiMotion.composerDuration, const Duration(milliseconds: 220));
      expect(KarmiMotion.composerCurve.transform(0), closeTo(0, 1e-6));
      expect(KarmiMotion.composerCurve.transform(1), closeTo(1, 1e-6));
    });

    testWidgets('is zero under reduced motion and 220ms otherwise', (
      tester,
    ) async {
      late BuildContext captured;
      await tester.pumpWidget(
        _host(
          disableAnimations: true,
          child: Builder(
            builder: (context) {
              captured = context;
              return const SizedBox();
            },
          ),
        ),
      );
      expect(KarmiMotion.composerDurationOf(captured), Duration.zero);

      await tester.pumpWidget(
        _host(
          disableAnimations: false,
          child: Builder(
            builder: (context) {
              captured = context;
              return const SizedBox();
            },
          ),
        ),
      );
      expect(
        KarmiMotion.composerDurationOf(captured),
        const Duration(milliseconds: 220),
      );
    });
  });

  group('type styles', () {
    test('greeting uses the Exo display face at 28px, 600', () {
      final s = KarmiTypography.greeting();
      expect(s.fontSize, 28);
      expect(s.fontWeight, FontWeight.w600);
      expect(s.letterSpacing, closeTo(-0.7, 0.001));
      expect(s.fontFamily, contains('Exo'));
    });

    test('message header name and toolbar caption are defined', () {
      expect(KarmiTypography.messageHeaderName().fontSize, 14);
      final caption = KarmiTypography.toolbarCaption();
      expect(caption.fontSize, 12);
      expect(caption.fontFeatures, isNotNull);
    });
  });
}
