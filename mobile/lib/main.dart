import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'theme/karmi_theme.dart';
import 'theme/karmi_glass.dart';
import 'theme/karmi_motion.dart';
import 'api/karmi_api.dart';
import 'shell/karmi_shell.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Disable runtime fetching for Google Fonts since we bundle them
  // Note: API validation needed (GoogleFonts.config.allowRuntimeFetching = false;)

  await LiquidGlassWidgets.initialize();

  final settingsProvider = KarmiSettingsProvider();
  await settingsProvider.initialize();

  // Set up API client with mock dev token placeholder
  final api = KarmiApi(
    baseUrl: const String.fromEnvironment('API_BASE_URL',
        defaultValue: 'http://10.0.2.2:8000'),
    token: 'dev_mock_token_placeholder',
  );

  runApp(KarmiApp(settingsProvider: settingsProvider, api: api));
}

class KarmiApp extends StatelessWidget {
  final KarmiSettingsProvider settingsProvider;
  final KarmiApi api;

  const KarmiApp({
    super.key,
    required this.settingsProvider,
    required this.api,
  });

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: settingsProvider,
      builder: (context, _) {
        return LiquidGlassWidgets.wrap(
          brightnessResolver: Theme.maybeBrightnessOf,
          adaptiveQuality: true,
          theme: KarmiGlass.themeData(context,
              brightness: Brightness.light), // We pass contextual theme later
          child: MaterialApp(
            title: 'Karmi',
            theme: KarmiTheme.light,
            darkTheme: KarmiTheme.dark,
            themeMode: settingsProvider.themeMode,
            builder: (context, child) {
              return KarmiMotion(
                isReduceTransparencyEnabled:
                    settingsProvider.reduceTransparency,
                isReduceMotionEnabled: MediaQuery.disableAnimationsOf(context),
                child: Material(
                  type: MaterialType.transparency,
                  child: child!,
                ),
              );
            },
            home: KarmiShell(api: api, settingsProvider: settingsProvider),
          ),
        );
      },
    );
  }
}
