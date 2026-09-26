import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/app.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/theme/karmi_glass.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'fake_backend.dart';

/// Reference phone viewport (logical px) used for layout tests and goldens.
const kPhoneSize = Size(412, 915);

class Env {
  const Env({
    this.brightness = Brightness.light,
    this.textScale = 1.0,
    this.reduceTransparency = false,
    this.reduceMotion = false,
    this.highContrast = false,
  });

  final Brightness brightness;
  final double textScale;
  final bool reduceTransparency;
  final bool reduceMotion;
  final bool highContrast;

  String get name =>
      '${brightness.name}_x${textScale.toStringAsFixed(1)}'
      '_${reduceTransparency ? 'opaque' : 'glass'}';
}

/// light/dark × text scale 1.0/2.0 × reduce transparency off/on (§8 goldens).
final goldenEnvs = [
  for (final b in Brightness.values)
    for (final s in [1.0, 2.0])
      for (final rt in [false, true])
        Env(brightness: b, textScale: s, reduceTransparency: rt),
];

/// Goldens are stored per host OS because text rasterisation differs between
/// platforms; CI (ubuntu-latest) compares against `goldens/linux/`.
String goldenPath(String name) =>
    'goldens/${Platform.operatingSystem}/$name.png';

Future<KarmiSettings> _settings(Env env) async {
  SharedPreferences.setMockInitialValues({
    'reduce_transparency': env.reduceTransparency,
    'theme_mode': env.brightness == Brightness.dark ? 'dark' : 'light',
  });
  return KarmiSettings(await SharedPreferences.getInstance());
}

void _applyView(WidgetTester tester, Env env, Size size) {
  tester.view
    ..physicalSize = size
    ..devicePixelRatio = 1.0;
  tester.platformDispatcher
    ..textScaleFactorTestValue = env.textScale
    ..accessibilityFeaturesTestValue = FakeAccessibilityFeatures(
      disableAnimations: env.reduceMotion,
      highContrast: env.highContrast,
    );
  addTearDown(() {
    tester.view.reset();
    tester.platformDispatcher.clearAllTestValues();
  });
}

/// Pumps [child] under the real Karmi theme, glass setup and accessibility builder.
Future<KarmiSettings> pumpHost(
  WidgetTester tester,
  Widget child, {
  Env env = const Env(),
  Size size = kPhoneSize,
}) async {
  _applyView(tester, env, size);
  final settings = await _settings(env);
  await tester.pumpWidget(
    LiquidGlassWidgets.wrap(
      theme: KarmiGlass.themeData(),
      brightnessResolver: Theme.maybeBrightnessOf,
      child: ListenableBuilder(
        listenable: settings,
        builder: (context, _) => MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: KarmiTheme.light,
          darkTheme: KarmiTheme.dark,
          highContrastTheme: KarmiTheme.highContrastLight,
          highContrastDarkTheme: KarmiTheme.highContrastDark,
          themeMode: settings.themeMode,
          builder: karmiAccessibilityBuilder(settings),
          home: Scaffold(body: child),
        ),
      ),
    ),
  );
  await settle(tester);
  return settings;
}

class AppHandle {
  AppHandle(this.settings, this.session, this.backend);

  final KarmiSettings settings;
  final KarmiSession session;
  final FakeBackend backend;
}

/// Pumps the whole app (KarmiApp) against [backend].
Future<AppHandle> pumpApp(
  WidgetTester tester, {
  FakeBackend? backend,
  Env env = const Env(),
  bool signedIn = true,
  Size size = kPhoneSize,
}) async {
  _applyView(tester, env, size);
  backend ??= FakeBackend.healthy();
  SharedPreferences.setMockInitialValues({
    'reduce_transparency': env.reduceTransparency,
    'theme_mode': env.brightness == Brightness.dark ? 'dark' : 'light',
    if (signedIn) 'dev_session_token': 'test-token',
  });
  final prefs = await SharedPreferences.getInstance();
  final settings = KarmiSettings(prefs);
  final session = KarmiSession(
    api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
    prefs: prefs,
  );
  await tester.pumpWidget(
    KarmiApp(settings: settings, session: session, adaptiveGlassQuality: false),
  );
  await settle(tester);
  return AppHandle(settings, session, backend);
}

/// Pumps until fonts, futures and glass springs settle. Glass widgets can keep
/// scheduling frames, so this pumps a bounded number of frames instead of
/// `pumpAndSettle`.
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 20; i++) {
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// Selects a shell tab by its label in either the glass or the opaque shell.
Future<void> openTab(WidgetTester tester, String label) async {
  final opaque = find.descendant(
    of: find.byType(NavigationBar),
    matching: find.text(label),
  );
  if (opaque.evaluate().isNotEmpty) {
    await tester.tap(opaque);
  } else {
    await tester.tap(find.bySemanticsLabel('$label tab').first);
  }
  await settle(tester);
}

/// §8 screen-reader / tap-target / contrast guidelines.
Future<void> expectA11yGuidelines(WidgetTester tester) async {
  final handle = tester.ensureSemantics();
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
  handle.dispose();
}

/// Fails if any RenderFlex overflowed (text scale 2.0 gate).
void expectNoOverflow(WidgetTester tester) {
  final error = tester.takeException();
  expect(error, isNull, reason: 'layout exception: $error');
}
