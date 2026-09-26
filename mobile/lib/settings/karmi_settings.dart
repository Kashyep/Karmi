import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Locally persisted display preferences (theme mode, reduce transparency).
class KarmiSettings extends ChangeNotifier {
  KarmiSettings(this._prefs)
    : _reduceTransparency = _prefs.getBool(_keyReduceTransparency) ?? false,
      _themeMode = ThemeMode.values.firstWhere(
        (m) => m.name == _prefs.getString(_keyThemeMode),
        orElse: () => ThemeMode.system,
      );

  static const _keyReduceTransparency = 'reduce_transparency';
  static const _keyThemeMode = 'theme_mode';

  final SharedPreferences _prefs;
  bool _reduceTransparency;
  ThemeMode _themeMode;

  bool get reduceTransparency => _reduceTransparency;
  ThemeMode get themeMode => _themeMode;

  Future<void> setReduceTransparency(bool value) async {
    _reduceTransparency = value;
    notifyListeners();
    await _prefs.setBool(_keyReduceTransparency, value);
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    _themeMode = mode;
    notifyListeners();
    await _prefs.setString(_keyThemeMode, mode.name);
  }
}
