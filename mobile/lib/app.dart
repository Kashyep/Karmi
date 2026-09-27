import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'armory/armory_controller.dart';
import 'auth/session.dart';
import 'features/welcome/welcome_screen.dart';
import 'settings/karmi_settings.dart';
import 'shell/karmi_shell.dart';
import 'theme/karmi_glass.dart';
import 'theme/karmi_motion.dart';
import 'theme/karmi_theme.dart';

/// Root widget and dual-axis theme provider (implementation_plan.md §2.1):
/// mode (System/Light/Dark, [KarmiSettings]) × tier ([ArmoryController]).
/// Both are applied once at the root — the Flutter equivalent of
/// `<html data-theme data-tier>` — by picking a cached [ThemeData].
class KarmiApp extends StatefulWidget {
  const KarmiApp({
    super.key,
    required this.settings,
    required this.session,
    required this.armory,
    this.adaptiveGlassQuality = true,
  });

  final KarmiSettings settings;
  final KarmiSession session;
  final ArmoryController armory;

  /// Runs liquid_glass_widgets' device benchmark. Off in widget tests.
  final bool adaptiveGlassQuality;

  @override
  State<KarmiApp> createState() => _KarmiAppState();
}

class _KarmiAppState extends State<KarmiApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  late bool _signedIn = widget.session.isSignedIn;

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_onSession);
    if (_signedIn) _loadArmory();
  }

  @override
  void dispose() {
    widget.session.removeListener(_onSession);
    super.dispose();
  }

  /// Progression is server-authoritative; a failed fetch keeps the cached
  /// (already clamped) tier, and 401s are handled by the session.
  Future<void> _loadArmory() async {
    try {
      await widget.armory.load();
    } on Exception {
      // Keep the cached tier; the Armory screen offers a retry.
    }
  }

  /// Sign-in loads the tier; sign-out or 401 drops pushed routes so Welcome
  /// is on top and forgets the account's tier.
  void _onSession() {
    final signedIn = widget.session.isSignedIn;
    if (_signedIn && !signedIn) {
      _navigatorKey.currentState?.popUntil((route) => route.isFirst);
      widget.armory.reset();
    } else if (!_signedIn && signedIn) {
      _loadArmory();
    }
    setState(() => _signedIn = signedIn);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([widget.settings, widget.armory]),
      builder: (context, _) {
        final tier = widget.armory.effectiveTier;
        return LiquidGlassWidgets.wrap(
          theme: KarmiGlass.themeData(tier),
          brightnessResolver: Theme.maybeBrightnessOf,
          adaptiveQuality: widget.adaptiveGlassQuality,
          child: MaterialApp(
            navigatorKey: _navigatorKey,
            title: 'Karmi',
            debugShowCheckedModeBanner: false,
            theme: KarmiTheme.of(tier, Brightness.light),
            darkTheme: KarmiTheme.of(tier, Brightness.dark),
            highContrastTheme: KarmiTheme.of(
              tier,
              Brightness.light,
              highContrast: true,
            ),
            highContrastDarkTheme: KarmiTheme.of(
              tier,
              Brightness.dark,
              highContrast: true,
            ),
            themeMode: widget.settings.themeMode,
            themeAnimationDuration: Duration.zero,
            builder: karmiAccessibilityBuilder(widget.settings),
            home: _signedIn
                ? KarmiShell(
                    key: const ValueKey('shell'),
                    api: widget.session.api,
                    settings: widget.settings,
                    session: widget.session,
                    armory: widget.armory,
                  )
                : WelcomeScreen(
                    key: const ValueKey('welcome'),
                    session: widget.session,
                  ),
          ),
        );
      },
    );
  }
}

/// `MaterialApp.builder`: resolves reduce transparency (setting OR platform
/// high contrast) and reduced motion once, for Karmi widgets and glass widgets.
TransitionBuilder karmiAccessibilityBuilder(KarmiSettings settings) =>
    (context, child) {
      final reduceTransparency =
          settings.reduceTransparency || MediaQuery.highContrastOf(context);
      final reduceMotion = MediaQuery.disableAnimationsOf(context);
      return KarmiAccessibility(
        reduceTransparency: reduceTransparency,
        reduceMotion: reduceMotion,
        child: GlassAccessibilityScope(
          reduceTransparency: reduceTransparency,
          reduceMotion: reduceMotion,
          // liquid_glass_widgets "Known Limitations": no yellow underlines.
          child: Material(type: MaterialType.transparency, child: child),
        ),
      );
    };
