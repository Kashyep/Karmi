import 'dart:async';

import 'package:flutter/foundation.dart' show debugOnRebuildDirtyWidget;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/armory/preview_banner.dart';
import 'package:karmi_app/features/armory/armory_screen.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/shell/chat_header.dart';
import 'package:karmi_app/theme/karmi_glass.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

const _historyKey = ValueKey('chat-header-history');
const _newChatKey = ValueKey('chat-header-new-chat');
const _bannerKey = ValueKey('armory-preview-banner');
const _modes = [('glass', Env()), ('solid', Env(reduceTransparency: true))];

/// Finds the app bar of the active mode: [GlassAppBar] or Material [AppBar].
Finder _appBarOf(Env env) =>
    env.reduceTransparency ? find.byType(AppBar) : find.byType(GlassAppBar);

void main() {
  group('Phase 6 app bar and preview banner', () {
    for (final (mode, env) in _modes) {
      testWidgets('$mode: preview banner never overlaps header controls', (
        tester,
      ) async {
        final app = await pumpApp(tester, env: env);
        app.armory.startPreview(KarmiTier.parth);
        await tester.pump();

        final banner = tester.getRect(find.byKey(_bannerKey));
        expect(
          banner.overlaps(tester.getRect(find.byKey(_historyKey))),
          isFalse,
        );
        expect(
          banner.overlaps(tester.getRect(find.byKey(_newChatKey))),
          isFalse,
        );
        expect(
          banner.top,
          greaterThan(tester.getRect(find.byKey(_historyKey)).bottom),
        );
        app.armory.endPreview();
        await tester.pump();
      });

      testWidgets('$mode: preview banner never overlaps the app bar', (
        tester,
      ) async {
        final app = await pumpApp(tester, env: env);
        app.armory.startPreview(KarmiTier.parth);
        await openTab(tester, 'Settings');
        await tester.pump();

        final banner = tester.getRect(find.byKey(_bannerKey));
        final appBar = tester.getRect(_appBarOf(env));
        expect(banner.overlaps(appBar), isFalse);
        expect(banner.top, greaterThanOrEqualTo(appBar.bottom));
        app.armory.endPreview();
        await tester.pump();
      });

      testWidgets('$mode: no overflow menu, no Plans text in the header', (
        tester,
      ) async {
        await pumpApp(tester, env: env);
        expect(find.byTooltip('More options'), findsNothing);
        expect(find.byIcon(Icons.menu), findsNothing);
        expect(
          find.descendant(
            of: find.byType(KarmiChatHeader),
            matching: find.text('Plans'),
          ),
          findsNothing,
        );
        await openTab(tester, 'Tasks');
        expect(find.byTooltip('More options'), findsNothing);
        expect(find.byIcon(Icons.menu), findsNothing);
      });

      testWidgets('$mode: Settings shows its title once', (tester) async {
        await pumpApp(tester, env: env);
        await openTab(tester, 'Settings');
        expect(
          find.descendant(of: _appBarOf(env), matching: find.text('Settings')),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: find.byType(ListView).first,
            matching: find.text('Settings'),
          ),
          findsNothing,
        );
      });

      testWidgets('$mode: Settings reaches Armory, Plans and Licences', (
        tester,
      ) async {
        await pumpApp(tester, env: env);
        await openTab(tester, 'Settings');

        await tester.tap(find.text('Armory'));
        await settle(tester);
        expect(find.byType(ArmoryScreen), findsOneWidget);
        await tester.pageBack();
        await settle(tester);

        await tester.tap(find.text('Plans and access code'));
        await settle(tester);
        expect(find.byType(PlanSelectionScreen), findsOneWidget);
        await tester.pageBack();
        await settle(tester);

        await tester.tap(find.text('Licences'));
        await settle(tester);
        expect(find.byType(LicensePage), findsOneWidget);
      });
    }

    testWidgets('glass and solid modes place header controls identically', (
      tester,
    ) async {
      Future<Map<String, Rect>> measure(Env env) async {
        await tester.pumpWidget(const SizedBox());
        await pumpApp(tester, size: const Size(412, 800), env: env);
        final rects = {
          'history': tester.getRect(find.byKey(_historyKey)),
          'newChat': tester.getRect(find.byKey(_newChatKey)),
        };
        await openTab(tester, 'Settings');
        rects['settingsTitle'] = tester.getRect(
          find.descendant(of: _appBarOf(env), matching: find.text('Settings')),
        );
        return rects;
      }

      final glass = await measure(const Env());
      final solid = await measure(const Env(reduceTransparency: true));
      expect(solid['history'], glass['history']);
      expect(solid['newChat'], glass['newChat']);
      expect(solid['settingsTitle'], glass['settingsTitle']);
    });

    testWidgets('New chat is disabled while a send is pending', (tester) async {
      final pending = Completer<http.Response>();
      final backend = FakeBackend.healthy()
        ..on('POST', '/v1/chat/stream', (_) => pending.future)
        ..on('POST', '/v1/messages', (_) => pending.future);
      await pumpApp(tester, backend: backend);

      IconButton newChat() =>
          tester.widget<IconButton>(find.byKey(_newChatKey));
      expect(newChat().onPressed, isNotNull);

      await tester.enterText(find.byType(TextField), 'Hello');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await settle(tester);

      expect(newChat().onPressed, isNull);
      await tester.tap(find.byKey(_newChatKey));
      await settle(tester);
      expect(find.text('Hello'), findsWidgets);

      pending.complete(
        http.Response(
          'event: run.started\n'
          'data: {"run_id":"r1","conversation_id":"c1","user_message_id":"u1",'
          '"assistant_message_id":"a1","seq":0}\n\n'
          'event: run.finished\n'
          'data: {"finish_reason":"stop","outcome":"ASK_USER"}\n\n',
          200,
          headers: {'content-type': 'text/event-stream'},
        ),
      );
      await settle(tester);
      expect(newChat().onPressed, isNotNull);
    });

    testWidgets('countdown rebuilds only its text each second', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final backend = FakeBackend.healthy();
      final armory = ArmoryController(
        api: KarmiApi(baseUrl: 'http://fake.test', client: backend.client),
        prefs: prefs,
      );
      addTearDown(armory.dispose);

      await tester.pumpWidget(
        LiquidGlassWidgets.wrap(
          child: MaterialApp(
            theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
            home: Scaffold(
              body: Stack(
                children: [
                  ListenableBuilder(
                    listenable: armory,
                    builder: (_, _) => ArmoryPreviewBanner(armory: armory),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      armory.startPreview(KarmiTier.parth);
      await tester.pump();
      expect(find.textContaining('Previewing Parth'), findsOneWidget);

      final rebuilt = <Type>[];
      final previous = debugOnRebuildDirtyWidget;
      debugOnRebuildDirtyWidget = (element, _) =>
          rebuilt.add(element.widget.runtimeType);
      addTearDown(() => debugOnRebuildDirtyWidget = previous);

      await tester.pump(const Duration(seconds: 1));
      expect(rebuilt, isNot(contains(ArmoryPreviewBanner)));
      expect(rebuilt, isNot(contains(KarmiGlassSurface)));
      expect(rebuilt, isNot(contains(TextButton)));
      expect(rebuilt, isNot(contains(ListenableBuilder)));

      armory.endPreview();
      await tester.pump();
    });

    for (final brightness in Brightness.values) {
      for (final (mode, env) in _modes) {
        testWidgets('preview banner golden: $mode ${brightness.name}', (
          tester,
        ) async {
          final app = await pumpApp(
            tester,
            env: Env(
              brightness: brightness,
              reduceTransparency: env.reduceTransparency,
            ),
          );
          app.armory.startPreview(KarmiTier.parth);
          await settle(tester);
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile(
              goldenPath('app_bar_preview_${mode}_${brightness.name}'),
            ),
          );
          app.armory.endPreview();
          await tester.pump();
        });
      }
    }
  });
}
