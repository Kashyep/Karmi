import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/karmi_api.dart';
import 'app.dart';
import 'armory/armory_controller.dart';
import 'auth/session.dart';
import 'fonts.dart';
import 'settings/karmi_settings.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  configureBundledFonts();
  await LiquidGlassWidgets.initialize();

  final prefs = await SharedPreferences.getInstance();
  final api = KarmiApi();
  final session = KarmiSession(api: api, prefs: prefs);

  runApp(
    KarmiApp(
      settings: KarmiSettings(prefs),
      session: session,
      armory: ArmoryController(api: api, prefs: prefs),
    ),
  );
}
