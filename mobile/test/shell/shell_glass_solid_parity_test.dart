import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../support/harness.dart';

const _historyKey = ValueKey('chat-header-history');
const _newChatKey = ValueKey('chat-header-new-chat');

void main() {
  group('Shell glass vs solid layout parity', () {
    setUpAll(() async {
      try {
        await LiquidGlassWidgets.initialize();
      } catch (_) {}
    });
    Future<void> fontsReady(WidgetTester tester) async {
      await tester.runAsync(GoogleFonts.pendingFonts);
      await settle(tester);
    }

    testWidgets(
      'compact phone (400x860): control positions, title position and tab-bar Rect are identical in glass vs solid on Chat, Usage and Settings',
      (tester) async {
        const phoneSize = Size(400, 860);

        Future<Map<String, dynamic>> measureTab(
          String tab, {
          required bool solid,
        }) async {
          await tester.pumpWidget(const SizedBox());
          await pumpApp(
            tester,
            size: phoneSize,
            env: Env(reduceTransparency: solid),
          );
          if (tab != 'Chat') {
            await openTab(tester, tab);
          }
          await settle(tester);

          final result = <String, dynamic>{};
          result['tabBarRect'] = tester.getRect(find.byType(GlassTabBar));

          // Tab semantics labels must match in both modes
          for (final name in ['Chat', 'Tasks', 'Usage', 'Settings']) {
            final semantics = find.bySemanticsLabel('$name tab');
            expect(semantics, findsOneWidget);
            result['tabRect_$name'] = tester.getRect(semantics);
          }

          if (tab == 'Chat') {
            result['historyRect'] = tester.getRect(find.byKey(_historyKey));
            result['newChatRect'] = tester.getRect(find.byKey(_newChatKey));
            result['titleRect'] = tester.getRect(
              find.descendant(
                of: find.byType(SafeArea).first,
                matching: find.text('New chat'),
              ),
            );
          } else {
            result['titleRect'] = tester.getRect(
              find.descendant(
                of: find.byType(GlassAppBar),
                matching: find.text(tab),
              ),
            );
          }
          return result;
        }

        for (final tab in ['Chat', 'Usage', 'Settings']) {
          final glass = await measureTab(tab, solid: false);
          final solid = await measureTab(tab, solid: true);

          expect(
            solid['tabBarRect'],
            glass['tabBarRect'],
            reason: '$tab: tab-bar Rect must be identical in glass vs solid',
          );
          expect(
            solid['titleRect'],
            glass['titleRect'],
            reason: '$tab: title position must be identical in glass vs solid',
          );

          for (final name in ['Chat', 'Tasks', 'Usage', 'Settings']) {
            expect(
              solid['tabRect_$name'],
              glass['tabRect_$name'],
              reason:
                  '$tab: $name tab position must be identical in glass vs solid',
            );
          }

          if (tab == 'Chat') {
            expect(
              solid['historyRect'],
              glass['historyRect'],
              reason: 'Chat: history icon position must be identical',
            );
            expect(
              solid['newChatRect'],
              glass['newChatRect'],
              reason: 'Chat: new-chat button position must be identical',
            );
          }
        }
      },
    );

    testWidgets(
      'wide layout (1024x768): rail Rect, destinations and title positions are identical in glass vs solid',
      (tester) async {
        const wideSize = Size(1024, 768);

        Future<Map<String, dynamic>> measureWide(
          String tab, {
          required bool solid,
        }) async {
          await tester.pumpWidget(const SizedBox());
          await pumpApp(
            tester,
            size: wideSize,
            env: Env(reduceTransparency: solid),
          );
          if (tab != 'Chat') {
            await openTab(tester, tab);
          }
          await settle(tester);

          final result = <String, dynamic>{};
          result['railRect'] = tester.getRect(find.byType(NavigationRail));

          for (final name in ['Chat', 'Tasks', 'Usage', 'Settings']) {
            final dest = find.descendant(
              of: find.byType(NavigationRail),
              matching: find.text(name),
            );
            expect(dest, findsOneWidget);
            result['railDest_$name'] = tester.getRect(dest);
          }
          if (tab == 'Chat') {
            result['historyRect'] = tester.getRect(find.byKey(_historyKey));
            result['newChatRect'] = tester.getRect(find.byKey(_newChatKey));
          } else {
            result['titleRect'] = tester.getRect(
              find.descendant(
                of: find.byType(GlassAppBar),
                matching: find.text(tab),
              ),
            );
          }
          return result;
        }

        for (final tab in ['Chat', 'Usage', 'Settings']) {
          final glass = await measureWide(tab, solid: false);
          final solid = await measureWide(tab, solid: true);

          expect(solid['railRect'], glass['railRect']);
          for (final name in ['Chat', 'Tasks', 'Usage', 'Settings']) {
            expect(solid['railDest_$name'], glass['railDest_$name']);
          }

          if (tab == 'Chat') {
            expect(solid['historyRect'], glass['historyRect']);
            expect(solid['newChatRect'], glass['newChatRect']);
          } else {
            expect(solid['titleRect'], glass['titleRect']);
          }
        }
      },
    );
    for (final brightness in Brightness.values) {
      for (final (mode, solid) in [('glass', false), ('solid', true)]) {
        for (final tab in ['chat', 'usage', 'settings']) {
          testWidgets('golden parity $tab: $mode ${brightness.name}', (
            tester,
          ) async {
            await pumpApp(
              tester,
              size: const Size(400, 860),
              env: Env(brightness: brightness, reduceTransparency: solid),
            );
            if (tab != 'chat') {
              final label = tab == 'usage' ? 'Usage' : 'Settings';
              await openTab(tester, label);
            }
            await fontsReady(tester);
            await expectLater(
              find.byType(MaterialApp),
              matchesGoldenFile(
                goldenPath('shell_parity_${tab}_${mode}_${brightness.name}'),
              ),
            );
          }, tags: ['golden']);
        }
      }
    }
  });
}
