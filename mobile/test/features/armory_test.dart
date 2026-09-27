import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/armory/armory_screen.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

/// The tier the running app currently renders.
KarmiTier renderedTier(WidgetTester tester) =>
    KarmiTierTheme.of(tester.element(find.byType(Navigator).first));

Color canvas(WidgetTester tester) => Theme.of(
  tester.element(find.byType(Navigator).first),
).scaffoldBackgroundColor;

/// Scrolls [target] into view in the Armory list and taps it.
Future<void> tapInArmory(WidgetTester tester, Finder target) async {
  await tester.scrollUntilVisible(
    target,
    200,
    scrollable: find
        .descendant(
          of: find.byType(ArmoryScreen),
          matching: find.byType(Scrollable),
        )
        .first,
  );
  await tester.ensureVisible(target);
  await tester.pump();
  await tester.tap(target);
}

Future<void> openArmory(WidgetTester tester) async {
  await tester.tap(find.byTooltip('More options'));
  await settle(tester);
  await tester.tap(find.text('Armory').last);
  await settle(tester);
}

Finder activateButton(KarmiTier tier) => find.descendant(
  of: find.byKey(ValueKey('tier-card-${tier.name}')),
  matching: find.byType(FilledButton),
);

void main() {
  testWidgets('app starts in the server tier and theme mode', (tester) async {
    await pumpApp(
      tester,
      env: const Env(tier: KarmiTier.trika, brightness: Brightness.dark),
    );
    expect(renderedTier(tester), KarmiTier.trika);
    expect(
      canvas(tester),
      KarmiColors.forTier(KarmiTier.trika, Brightness.dark).background,
    );
  });

  testWidgets('light/dark switch keeps the tier and persists', (tester) async {
    final app = await pumpApp(tester, env: const Env(tier: KarmiTier.yanta));
    await app.settings.setThemeMode(ThemeMode.dark);
    await settle(tester);
    expect(renderedTier(tester), KarmiTier.yanta);
    expect(
      canvas(tester),
      KarmiColors.forTier(KarmiTier.yanta, Brightness.dark).background,
    );
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('theme_mode'), 'dark');
  });

  testWidgets('gallery: four tiers, locked ones blurred and not activatable', (
    tester,
  ) async {
    final backend = FakeBackend.healthy(unlocked: KarmiTier.yanta);
    // Tall viewport: every card is laid out and none straddles the app bar.
    await pumpApp(tester, backend: backend, size: const Size(412, 2600));
    await openArmory(tester);
    expect(find.byType(ArmoryScreen), findsOneWidget);
    for (final tier in KarmiTier.values) {
      expect(find.byKey(ValueKey('tier-card-${tier.name}')), findsOneWidget);
      final locked = tier.id > 2;
      expect(
        find.byKey(ValueKey('locked-filter-${tier.name}')),
        locked ? findsOneWidget : findsNothing,
        reason: tier.label,
      );
      if (tier == KarmiTier.ananta) continue; // active: no activate button
      final button = tester.widget<FilledButton>(activateButton(tier));
      expect(button.onPressed, locked ? isNull : isNotNull, reason: tier.label);
    }
    expect(find.text('Trika'), findsWidgets);
    // Third tier is Trika (single k), never the double-k misspelling.
    expect(
      find.textContaining(RegExp('trik{2}a', caseSensitive: false)),
      findsNothing,
    );
    await expectA11yGuidelines(tester);
  });

  testWidgets('activating an unlocked tier re-themes the whole app', (
    tester,
  ) async {
    final backend = FakeBackend.healthy(unlocked: KarmiTier.parth);
    final app = await pumpApp(tester, backend: backend);
    await openArmory(tester);
    await tapInArmory(tester, activateButton(KarmiTier.parth));
    await settle(tester);
    expect(backend.activeTheme, 4);
    expect(renderedTier(tester), KarmiTier.parth);
    expect(app.icons.applied.last, KarmiTier.parth);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getInt('armory_active_theme'), 4);
    final put = backend.requests.lastWhere((r) => r.method == 'PUT');
    expect(jsonDecode(put.body), {'active_theme': 4});
  });

  testWidgets('10-second preview applies a locked tier then reverts', (
    tester,
  ) async {
    await pumpApp(tester);
    await openArmory(tester);
    await tapInArmory(tester, find.text('Preview 10 s').last); // Parth
    await tester.pump();
    expect(renderedTier(tester), KarmiTier.parth);
    expect(find.textContaining('Previewing Parth'), findsWidgets);
    await tester.pump(const Duration(seconds: 9));
    expect(renderedTier(tester), KarmiTier.parth);
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();
    expect(renderedTier(tester), KarmiTier.ananta);
    expect(find.textContaining('Previewing'), findsNothing);
  });

  testWidgets('End preview reverts immediately', (tester) async {
    await pumpApp(tester);
    await openArmory(tester);
    await tapInArmory(tester, find.text('Preview 10 s').first);
    await tester.pump();
    expect(renderedTier(tester), KarmiTier.yanta);
    await tester.tap(find.text('End preview').first);
    await tester.pump();
    expect(renderedTier(tester), KarmiTier.ananta);
  });

  testWidgets('server downgrade reverts the active theme on next load', (
    tester,
  ) async {
    final backend = FakeBackend.healthy(
      unlocked: KarmiTier.parth,
      active: KarmiTier.parth,
    );
    final app = await pumpApp(tester, backend: backend);
    expect(renderedTier(tester), KarmiTier.parth);
    backend.unlockedTier = 1;
    await openArmory(tester); // Armory re-validates with the server
    expect(renderedTier(tester), KarmiTier.ananta);
    expect(app.armory.activeTheme, KarmiTier.ananta);
  });

  testWidgets('sign-out returns to the default tier', (tester) async {
    final app = await pumpApp(
      tester,
      env: const Env(tier: KarmiTier.trika, brightness: Brightness.dark),
    );
    await app.session.signOut();
    await settle(tester);
    expect(app.armory.effectiveTier, KarmiTier.ananta);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getInt('armory_active_theme'), isNull);
  });

  testWidgets('agent behaviour is identical in every tier', (tester) async {
    final bodies = <Object?>[];
    for (final tier in KarmiTier.values) {
      await tester.pumpWidget(const SizedBox()); // fresh app per tier
      final backend = FakeBackend.healthy(unlocked: tier, active: tier);
      await pumpApp(
        tester,
        backend: backend,
        env: Env(tier: tier),
      );
      await tester.enterText(find.byType(TextField), 'Remind me at 9');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await settle(tester);
      expect(
        find.descendant(
          of: find.byType(ChatScreen),
          matching: find.text('Completed'),
        ),
        findsOneWidget,
        reason: tier.label,
      );
      final post = backend.requests.singleWhere(
        (r) => r.url.path == '/v1/messages',
      );
      final body = jsonDecode(post.body) as Map;
      bodies.add(body['text']);
      expect(body.keys, unorderedEquals(['text', 'idempotency_key']));
    }
    expect(bodies.toSet(), {'Remind me at 9'});
  });

  for (final tier in KarmiTier.values) {
    for (final brightness in Brightness.values) {
      testWidgets('a11y guidelines: ${tier.label} ${brightness.name}', (
        tester,
      ) async {
        await pumpApp(
          tester,
          // Tall viewport: the whole gallery (incl. locked cards) is on screen
          // without scrolling, so no text straddles the app bar.
          size: const Size(412, 2600),
          env: Env(tier: tier, brightness: brightness),
          backend: FakeBackend.healthy(
            unlocked: tier == KarmiTier.parth ? tier : KarmiTier.trika,
            active: tier,
          ),
        );
        await expectA11yGuidelines(tester); // chat + glass chrome
        await openTab(tester, 'Settings');
        await expectA11yGuidelines(tester);
        await openArmory(tester);
        await expectA11yGuidelines(tester);
        await expectA11yGuidelines(tester); // locked cards, disabled buttons
      });
    }
  }
}
