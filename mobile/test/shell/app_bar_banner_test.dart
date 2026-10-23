import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:karmi_app/armory/preview_banner.dart';
import 'package:karmi_app/features/armory/armory_screen.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:karmi_app/shell/chat_header.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

void main() {
  group('Phase 6 AppBar and Preview Banner', () {
    testWidgets(
      'the banner never overlaps app-bar controls in glass mode',
      (tester) async {
        final app = await pumpApp(tester);
        app.armory.startPreview(KarmiTier.parth);
        await tester.pump();

        final banner = find.byKey(const ValueKey('armory-preview-banner'));
        expect(banner, findsOneWidget);

        final headerHistory = find.byKey(const ValueKey('chat-header-history'));
        final headerNewChat = find.byKey(const ValueKey('chat-header-new-chat'));

        final bannerRect = tester.getRect(banner);
        final historyRect = tester.getRect(headerHistory);
        final newChatRect = tester.getRect(headerNewChat);

        expect(bannerRect.top, greaterThanOrEqualTo(historyRect.bottom));
        expect(bannerRect.top, greaterThanOrEqualTo(newChatRect.bottom));
        app.armory.endPreview();
        await tester.pump();
      },
    );

    testWidgets(
      'the banner never overlaps app-bar controls in solid mode',
      (tester) async {
        final app = await pumpApp(
          tester,
          env: const Env(reduceTransparency: true),
        );
        app.armory.startPreview(KarmiTier.parth);
        await tester.pump();

        final banner = find.byKey(const ValueKey('armory-preview-banner'));
        expect(banner, findsOneWidget);

        final headerHistory = find.byKey(const ValueKey('chat-header-history'));
        final headerNewChat = find.byKey(const ValueKey('chat-header-new-chat'));

        final bannerRect = tester.getRect(banner);
        final historyRect = tester.getRect(headerHistory);
        final newChatRect = tester.getRect(headerNewChat);

        expect(bannerRect.top, greaterThanOrEqualTo(historyRect.bottom));
        expect(bannerRect.top, greaterThanOrEqualTo(newChatRect.bottom));
        app.armory.endPreview();
        await tester.pump();
      },
    );

    testWidgets(
      'the banner never overlaps AppBar on non-chat tabs in solid mode',
      (tester) async {
        final app = await pumpApp(
          tester,
          env: const Env(reduceTransparency: true),
        );
        app.armory.startPreview(KarmiTier.parth);
        await openTab(tester, 'Settings');
        await tester.pump();

        final banner = find.byKey(const ValueKey('armory-preview-banner'));
        expect(banner, findsOneWidget);

        final appBar = find.byType(AppBar);
        expect(appBar, findsOneWidget);

        final bannerRect = tester.getRect(banner);
        final appBarRect = tester.getRect(appBar);

        expect(bannerRect.top, greaterThanOrEqualTo(appBarRect.bottom));
        app.armory.endPreview();
        await tester.pump();
      },
    );
    testWidgets('same controls in glass mode (no hamburger swap)', (
      tester,
    ) async {
      await pumpApp(tester, size: const Size(412, 800));
      expect(find.byKey(const ValueKey('chat-header-history')), findsOneWidget);
      expect(find.byKey(const ValueKey('chat-header-new-chat')), findsOneWidget);
      expect(find.byIcon(Icons.menu), findsNothing);
      expect(find.text('Plans'), findsNothing); // Removed from chat app bar

      await openTab(tester, 'Tasks');
      expect(find.byIcon(Icons.menu), findsNothing);
    });

    testWidgets('same controls in solid mode (no hamburger swap)', (
      tester,
    ) async {
      await pumpApp(
        tester,
        size: const Size(412, 800),
        env: const Env(reduceTransparency: true),
      );
      expect(find.byKey(const ValueKey('chat-header-history')), findsOneWidget);
      expect(find.byKey(const ValueKey('chat-header-new-chat')), findsOneWidget);
      expect(find.byIcon(Icons.menu), findsNothing);
      expect(find.text('Plans'), findsNothing);

      await openTab(tester, 'Tasks');
      expect(find.byIcon(Icons.menu), findsNothing);
    });

    testWidgets('Settings reaches Armory, Plans, Licences', (tester) async {
      await pumpApp(tester);
      await openTab(tester, 'Settings');

      // 1. Armory
      expect(find.text('Armory'), findsOneWidget);
      await tester.tap(find.text('Armory'));
      await settle(tester);
      expect(find.byType(ArmoryScreen), findsOneWidget);

      await tester.pageBack();
      await settle(tester);

      // 2. Plans and access code
      expect(find.text('Plans and access code'), findsOneWidget);
      await tester.tap(find.text('Plans and access code'));
      await settle(tester);
      expect(find.byType(PlanSelectionScreen), findsOneWidget);

      await tester.pageBack();
      await settle(tester);

      // 3. Licences
      expect(find.text('Licences'), findsOneWidget);
      await tester.tap(find.text('Licences'));
      await settle(tester);
      expect(find.byType(LicensePage), findsOneWidget);
    });

    testWidgets('New chat disabled while pending', (tester) async {
      bool newChatCalled = false;

      await tester.pumpWidget(
        MaterialApp(
          theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
          home: Scaffold(
            body: KarmiChatHeader(
              title: 'Test Conversation',
              onNewChat: null, // Disabled when pending / busy
              onOpenHistory: () {},
            ),
          ),
        ),
      );

      final newChatBtn = find.byKey(const ValueKey('chat-header-new-chat'));
      expect(newChatBtn, findsOneWidget);

      final iconButton = tester.widget<IconButton>(newChatBtn);
      expect(iconButton.onPressed, isNull);

      // Tap should do nothing
      await tester.tap(newChatBtn);
      expect(newChatCalled, isFalse);
    });

    testWidgets(
      'countdown rebuilds only its text without rebuilding banner tree',
      (tester) async {
        final backend = FakeBackend.healthy();
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final armory = ArmoryController(
          api: KarmiApi(baseUrl: 'http://fake.test', client: backend.client),
          prefs: prefs,
        );

        int buildCount = 0;
        await tester.pumpWidget(
          LiquidGlassWidgets.wrap(
            child: MaterialApp(
              theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
              home: Scaffold(
                body: Builder(
                  builder: (context) {
                    buildCount++;
                    return ArmoryPreviewBanner(armory: armory);
                  },
                ),
              ),
            ),
          ),
        );

        armory.startPreview(KarmiTier.parth);
        await tester.pump();

        expect(find.textContaining('Previewing Parth'), findsOneWidget);
        final initialBuildCount = buildCount;

        // Advance timer by 1s
        await tester.pump(const Duration(seconds: 1));
        expect(find.textContaining('Previewing Parth'), findsOneWidget);

        // Outer tree did not rebuild
        expect(buildCount, equals(initialBuildCount));

        armory.endPreview();
        await tester.pump();
        armory.dispose();
      },
    );
  });
}
