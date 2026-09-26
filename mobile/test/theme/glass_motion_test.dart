import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_glass.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/widgets/feedback.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/harness.dart';

const _probe = KarmiGlassSurface(child: SizedBox(width: 100, height: 40));

void main() {
  group('reduce transparency', () {
    testWidgets('off: glass surface', (tester) async {
      await pumpHost(tester, const Center(child: _probe));
      expect(find.byKey(const ValueKey('karmi-glass')), findsOneWidget);
      expect(find.byKey(const ValueKey('karmi-glass-opaque')), findsNothing);
    });

    testWidgets('on: opaque --card with 1px --border', (tester) async {
      await pumpHost(
        tester,
        const Center(child: _probe),
        env: const Env(reduceTransparency: true),
      );
      expect(find.byType(GlassContainer), findsNothing);
      final box = tester.widget<DecoratedBox>(
        find.byKey(const ValueKey('karmi-glass-opaque')),
      );
      final decoration = box.decoration as BoxDecoration;
      expect(decoration.color, KarmiColors.light.card);
      expect(decoration.color!.a, 1.0);
      expect(
        (decoration.border! as Border).top.color,
        KarmiColors.light.border,
      );
      expect((decoration.border! as Border).top.width, 1.0);
    });

    testWidgets('platform high contrast forces the opaque fallback', (
      tester,
    ) async {
      await pumpHost(
        tester,
        const Center(child: _probe),
        env: const Env(highContrast: true),
      );
      expect(find.byType(GlassContainer), findsNothing);
      expect(find.byKey(const ValueKey('karmi-glass-opaque')), findsOneWidget);
    });

    testWidgets('shell swaps glass bars for opaque Material bars', (
      tester,
    ) async {
      await pumpApp(tester);
      expect(find.byType(GlassTabBar), findsOneWidget);
      expect(find.byType(GlassAppBar), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);

      await openTab(tester, 'Settings');
      await tester.tap(find.text('Reduce transparency'));
      await settle(tester);

      expect(find.byType(GlassTabBar), findsNothing);
      expect(find.byType(GlassAppBar), findsNothing);
      expect(find.byType(NavigationBar), findsOneWidget);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getBool('reduce_transparency'), isTrue);

      await tester.tap(find.text('Reduce transparency'));
      await settle(tester);
      expect(find.byType(GlassTabBar), findsOneWidget);
    });
  });

  group('high contrast', () {
    testWidgets('borders use the foreground colour, focus rings are 3px', (
      tester,
    ) async {
      late ThemeData theme;
      await pumpHost(
        tester,
        Builder(
          builder: (context) {
            theme = Theme.of(context);
            return const SizedBox();
          },
        ),
        env: const Env(highContrast: true),
      );
      final colors = theme.extension<KarmiColors>()!;
      expect(colors.border, KarmiColors.light.foreground);
      expect(colors.borderSubtle, KarmiColors.light.foreground);
      expect(theme.colorScheme.outline, KarmiColors.light.foreground);
      expect(theme.extension<KarmiShape>()!.focusRingWidth, 3);
      final side = theme.outlinedButtonTheme.style!.side!.resolve({
        WidgetState.focused,
      })!;
      expect(side.width, 3);
      expect(side.color, KarmiColors.light.ring);
      final idle = theme.outlinedButtonTheme.style!.side!.resolve({})!;
      expect(idle.color, KarmiColors.light.foreground);
      final input = theme.inputDecorationTheme.focusedBorder!.borderSide;
      expect(input.width, 3);
    });

    testWidgets('default contrast keeps token borders and 2px rings', (
      tester,
    ) async {
      late ThemeData theme;
      await pumpHost(
        tester,
        Builder(
          builder: (context) {
            theme = Theme.of(context);
            return const SizedBox();
          },
        ),
        env: const Env(brightness: Brightness.dark),
      );
      expect(theme.brightness, Brightness.dark);
      expect(theme.extension<KarmiColors>()!.border, KarmiColors.dark.border);
      expect(theme.extension<KarmiShape>()!.focusRingWidth, 2);
      final side = theme.filledButtonTheme.style!.side!.resolve({
        WidgetState.focused,
      })!;
      expect(side.width, 2);
    });

    testWidgets('a focused button paints the ring', (tester) async {
      final focus = FocusNode();
      addTearDown(focus.dispose);
      // Keyboard (traditional) highlight mode, as with a hardware keyboard.
      FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.alwaysTraditional;
      addTearDown(
        () => FocusManager.instance.highlightStrategy =
            FocusHighlightStrategy.automatic,
      );
      await pumpHost(
        tester,
        Center(
          child: OutlinedButton(
            focusNode: focus,
            onPressed: () {},
            child: const Text('Go'),
          ),
        ),
        env: const Env(highContrast: true),
      );
      focus.requestFocus();
      await tester.pump();
      await tester.pump();
      final material = tester.widget<Material>(
        find.descendant(
          of: find.byType(OutlinedButton),
          matching: find.byType(Material),
        ),
      );
      final shape = material.shape! as OutlinedBorder;
      expect(shape.side.width, 3);
      expect(shape.side.color, KarmiColors.light.ring);
    });
  });

  group('glass theme', () {
    test('both brightness variants carry their own tint floor', () {
      final data = KarmiGlass.themeData();
      expect(
        data.light.settings!.glassColor,
        KarmiColors.light.card.withValues(alpha: 0.72),
      );
      expect(
        data.dark.settings!.glassColor,
        KarmiColors.dark.card.withValues(alpha: 0.78),
      );
    });

    for (final brightness in Brightness.values) {
      testWidgets('resolves the ${brightness.name} variant in context', (
        tester,
      ) async {
        late BuildContext ctx;
        await pumpHost(
          tester,
          Builder(
            builder: (context) {
              ctx = context;
              return const SizedBox();
            },
          ),
          env: Env(brightness: brightness),
        );
        expect(GlassTheme.brightnessOf(ctx), brightness);
        final tint = GlassThemeData.of(ctx).settingsFor(ctx)!.glassColor;
        final card = brightness == Brightness.light
            ? KarmiColors.light.card
            : KarmiColors.dark.card;
        expect(tint!.withValues(alpha: 1), card);
      });
    }
  });

  group('reduced motion', () {
    testWidgets('off: 180ms transitions and a spinner', (tester) async {
      late BuildContext ctx;
      await pumpHost(
        tester,
        Builder(
          builder: (context) {
            ctx = context;
            return const Center(child: KarmiLoader());
          },
        ),
      );
      expect(KarmiMotion.duration(ctx), const Duration(milliseconds: 180));
      expect(KarmiMotion.duration(ctx, KarmiMotion.fast), KarmiMotion.fast);
      expect(
        find.byKey(const ValueKey('karmi-loader-spinner')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('karmi-loader-static')), findsNothing);
      expect(find.text('Working'), findsOneWidget);
    });

    testWidgets('on: Duration.zero and a static icon plus text', (
      tester,
    ) async {
      late BuildContext ctx;
      await pumpHost(
        tester,
        Builder(
          builder: (context) {
            ctx = context;
            return const Center(child: KarmiLoader());
          },
        ),
        env: const Env(reduceMotion: true),
      );
      expect(KarmiMotion.duration(ctx), Duration.zero);
      expect(KarmiMotion.duration(ctx, KarmiMotion.fast), Duration.zero);
      expect(find.byKey(const ValueKey('karmi-loader-static')), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.text('Working'), findsOneWidget);
    });

    for (final reduce in [false, true]) {
      testWidgets('page route ${reduce ? 'snaps' : 'fades'}', (tester) async {
        await pumpHost(
          tester,
          Builder(
            builder: (context) => TextButton(
              onPressed: () => Navigator.of(context).push(
                KarmiMotion.route<void>(
                  context,
                  (_) => const PlanSelectionScreen(),
                ),
              ),
              child: const Text('Open'),
            ),
          ),
          env: Env(reduceMotion: reduce),
        );
        await tester.tap(find.text('Open'));
        await tester.pump();
        await tester.pump();
        final fade = tester.widget<FadeTransition>(
          find
              .ancestor(
                of: find.byType(PlanSelectionScreen),
                matching: find.byType(FadeTransition),
              )
              .first,
        );
        if (reduce) {
          expect(fade.opacity.value, 1.0);
        } else {
          expect(fade.opacity.value, lessThan(1.0));
          await tester.pump(const Duration(milliseconds: 200));
          expect(fade.opacity.value, 1.0);
        }
      });
    }
  });
}
