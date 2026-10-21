import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/welcome/tester_notice.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/shell/history_panel.dart';
import 'package:karmi_app/shell/karmi_shell.dart';
import 'package:karmi_app/theme/karmi_glass.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

const _railMarker = 'history-rail-marker';

Future<void> _pumpShell(WidgetTester tester, double width) async {
  tester.view.physicalSize = Size(width, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);

  SharedPreferences.setMockInitialValues({
    'dev_session_token': 'token',
    'acknowledged_tester_notice_version': kTesterNoticeVersion,
  });
  final prefs = await SharedPreferences.getInstance();
  final settings = KarmiSettings(prefs);
  final backend = FakeBackend.healthy();
  final session = KarmiSession(
    api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
    prefs: prefs,
  );
  final armory = ArmoryController(
    api: session.api,
    prefs: prefs,
    appIcon: FakeAppIcons(),
  );
  addTearDown(armory.dispose);

  await tester.pumpWidget(
    LiquidGlassWidgets.wrap(
      theme: KarmiGlass.themeData(armory.effectiveTier),
      brightnessResolver: Theme.maybeBrightnessOf,
      adaptiveQuality: false,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: KarmiTheme.of(armory.effectiveTier, Brightness.light),
        home: KarmiShell(
          api: session.api,
          settings: settings,
          session: session,
          armory: armory,
          historyRailBuilder: (_) => const Text(_railMarker),
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 500));
}

void main() {
  testWidgets('compact (400): no persistent history rail', (tester) async {
    await _pumpShell(tester, 400);

    expect(find.text(_railMarker), findsNothing);
  });

  testWidgets(
    'tablet (800): history overlay hidden until header History button is tapped',
    (tester) async {
      await _pumpShell(tester, 800);

      final panel = find.byKey(const ValueKey('history-overlay-panel'));
      expect(
        tester.widget<AnimatedPositioned>(panel).left,
        -KarmiShape.historyRailWidth,
        reason: 'overlay must be slid off-screen before it is opened',
      );

      await tester.tap(find.byTooltip('Conversation history'));
      await tester.pump(const Duration(milliseconds: 500));

      expect(tester.widget<AnimatedPositioned>(panel).left, 0);
      expect(find.text(_railMarker), findsOneWidget);
    },
  );

  testWidgets('expanded (1200): history rail is persistent at 260px', (
    tester,
  ) async {
    await _pumpShell(tester, 1200);

    final marker = find.text(_railMarker);
    expect(marker, findsOneWidget);
    expect(
      tester
          .getSize(
            find.ancestor(of: marker, matching: find.byType(HistoryPanel)),
          )
          .width,
      260,
    );
  });
}
