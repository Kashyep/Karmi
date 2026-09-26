import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'auth/session.dart';
import 'features/welcome/welcome_screen.dart';
import 'settings/karmi_settings.dart';
import 'shell/karmi_shell.dart';
import 'theme/karmi_glass.dart';
import 'theme/karmi_motion.dart';
import 'theme/karmi_theme.dart';

/// Root widget: themes (incl. high-contrast variants), glass setup (§5) and the
/// signed-in / signed-out switch.
class KarmiApp extends StatefulWidget {
  const KarmiApp({
    super.key,
    required this.settings,
    required this.session,
    this.adaptiveGlassQuality = true,
  });

  final KarmiSettings settings;
  final KarmiSession session;

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
  }

  @override
  void dispose() {
    widget.session.removeListener(_onSession);
    super.dispose();
  }

  /// Sign-out or 401: drop any pushed routes so Welcome is on top.
  void _onSession() {
    if (_signedIn && !widget.session.isSignedIn) {
      _navigatorKey.currentState?.popUntil((route) => route.isFirst);
    }
    setState(() => _signedIn = widget.session.isSignedIn);
  }

  @override
  Widget build(BuildContext context) {
    return LiquidGlassWidgets.wrap(
      theme: KarmiGlass.themeData(),
      brightnessResolver: Theme.maybeBrightnessOf,
      adaptiveQuality: widget.adaptiveGlassQuality,
      child: ListenableBuilder(
        listenable: widget.settings,
        builder: (context, _) => MaterialApp(
          navigatorKey: _navigatorKey,
          title: 'Karmi',
          debugShowCheckedModeBanner: false,
          theme: KarmiTheme.light,
          darkTheme: KarmiTheme.dark,
          highContrastTheme: KarmiTheme.highContrastLight,
          highContrastDarkTheme: KarmiTheme.highContrastDark,
          themeMode: widget.settings.themeMode,
          themeAnimationDuration: Duration.zero,
          builder: karmiAccessibilityBuilder(widget.settings),
          home: _signedIn
              ? KarmiShell(
                  key: const ValueKey('shell'),
                  api: widget.session.api,
                  settings: widget.settings,
                  session: widget.session,
                )
              : WelcomeScreen(
                  key: const ValueKey('welcome'),
                  session: widget.session,
                ),
        ),
      ),
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
