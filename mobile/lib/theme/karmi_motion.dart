import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class KarmiMotion extends InheritedWidget {
  final bool isReduceTransparencyEnabled;
  final bool isReduceMotionEnabled;

  const KarmiMotion({
    super.key,
    required this.isReduceTransparencyEnabled,
    required this.isReduceMotionEnabled,
    required super.child,
  });

  static bool reduceTransparencyOf(BuildContext context) {
    final motion = context.dependOnInheritedWidgetOfExactType<KarmiMotion>();
    final highContrast = MediaQuery.highContrastOf(context);
    return highContrast || (motion?.isReduceTransparencyEnabled ?? false);
  }

  static bool reduceMotionOf(BuildContext context) {
    return MediaQuery.disableAnimationsOf(context);
  }

  @override
  bool updateShouldNotify(KarmiMotion oldWidget) {
    return oldWidget.isReduceTransparencyEnabled !=
            isReduceTransparencyEnabled ||
        oldWidget.isReduceMotionEnabled != isReduceMotionEnabled;
  }
}

class KarmiSettingsProvider extends ChangeNotifier {
  static const _keyReduceTransparency = 'reduce_transparency';
  static const _keyThemeMode = 'theme_mode';

  late SharedPreferences _prefs;
  bool _reduceTransparency = false;
  ThemeMode _themeMode = ThemeMode.system;

  bool get reduceTransparency => _reduceTransparency;
  ThemeMode get themeMode => _themeMode;

  Future<void> initialize() async {
    _prefs = await SharedPreferences.getInstance();
    _reduceTransparency = _prefs.getBool(_keyReduceTransparency) ?? false;

    final themeStr = _prefs.getString(_keyThemeMode);
    _themeMode = ThemeMode.values.firstWhere(
      (e) => e.name == themeStr,
      orElse: () => ThemeMode.system,
    );
    notifyListeners();
  }

  Future<void> setReduceTransparency(bool value) async {
    _reduceTransparency = value;
    await _prefs.setBool(_keyReduceTransparency, value);
    notifyListeners();
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    _themeMode = mode;
    await _prefs.setString(_keyThemeMode, mode.name);
    notifyListeners();
  }
}
