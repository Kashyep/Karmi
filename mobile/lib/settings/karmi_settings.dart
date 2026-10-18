import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Locally persisted display preferences (theme mode, reduce transparency).
class KarmiSettings extends ChangeNotifier {
  KarmiSettings(this._prefs)
    : _reduceTransparency = _prefs.getBool(_keyReduceTransparency) ?? false,
      _themeMode = ThemeMode.values.firstWhere(
        (m) => m.name == _prefs.getString(_keyThemeMode),
        orElse: () => ThemeMode.system,
      ),
      _acknowledgedNoticeVersion = _prefs.getInt(_keyTesterNoticeVersion) ?? 0,
      _apiBaseUrl = _prefs.getString(_keyApiBaseUrl);
  static const _keyReduceTransparency = 'reduce_transparency';
  static const _keyThemeMode = 'theme_mode';

  static const _keyApiBaseUrl = 'api_base_url';
  static const _keyTesterNoticeVersion = 'acknowledged_tester_notice_version';
  final SharedPreferences _prefs;
  bool _reduceTransparency;
  ThemeMode _themeMode;
  int _acknowledgedNoticeVersion;
  String? _apiBaseUrl;

  /// Tester-chosen server address; applies from the next app start.
  String? get apiBaseUrl => _apiBaseUrl;

  /// Accepts https URLs, plus plain http only for local development hosts.
  static bool isValidServerUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null || uri.host.isEmpty || uri.hasQuery || uri.fragment.isNotEmpty) {
      return false;
    }
    if (uri.scheme == 'https') return true;
    return uri.scheme == 'http' &&
        const {'localhost', '127.0.0.1', '10.0.2.2'}.contains(uri.host);
  }

  Future<void> setApiBaseUrl(String? value) async {
    final cleaned = value?.trim().replaceAll(RegExp(r'/+$'), '');
    _apiBaseUrl = (cleaned == null || cleaned.isEmpty) ? null : cleaned;
    notifyListeners();
    if (_apiBaseUrl == null) {
      await _prefs.remove(_keyApiBaseUrl);
    } else {
      await _prefs.setString(_keyApiBaseUrl, _apiBaseUrl!);
    }
  }

  bool get reduceTransparency => _reduceTransparency;
  ThemeMode get themeMode => _themeMode;
  int get acknowledgedNoticeVersion => _acknowledgedNoticeVersion;
  bool isTesterNoticeAcknowledged(int version) =>
      _acknowledgedNoticeVersion >= version;

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

  Future<void> acknowledgeTesterNotice(int version) async {
    _acknowledgedNoticeVersion = version;
    notifyListeners();
    await _prefs.setInt(_keyTesterNoticeVersion, version);
  }
}
