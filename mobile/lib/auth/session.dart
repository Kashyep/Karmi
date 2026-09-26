import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/karmi_api.dart';

/// `--dart-define=KARMI_DEV_AUTH=false` hides development sign-in. Defaults on
/// outside release mode. Production auth is out of scope (ADR-0002 Q3).
const bool kDevAuthEnabled = bool.fromEnvironment(
  'KARMI_DEV_AUTH',
  defaultValue: !kReleaseMode,
);

enum SessionEnd { none, signedOut, expired }

/// Holds the development bearer token issued by `POST /dev/token`.
///
/// Stored in SharedPreferences because it is a synthetic dev credential; a
/// production token would need platform secure storage.
class KarmiSession extends ChangeNotifier {
  KarmiSession({required this.api, required SharedPreferences prefs})
    : _prefs = prefs {
    api.token = _prefs.getString(_key);
    api.onUnauthorized = expire;
  }

  static const _key = 'dev_session_token';

  final KarmiApi api;
  final SharedPreferences _prefs;
  SessionEnd _lastEnd = SessionEnd.none;

  bool get isSignedIn => api.token != null;

  /// Why the previous session ended, for the Welcome screen copy.
  SessionEnd get lastEnd => _lastEnd;

  /// Throws [KarmiApiException] on failure; the token is unchanged then.
  Future<void> signInWithDevToken() async {
    final token = await api.issueDevToken();
    api.token = token;
    _lastEnd = SessionEnd.none;
    await _prefs.setString(_key, token);
    notifyListeners();
  }

  Future<void> signOut() => _end(SessionEnd.signedOut);

  /// Called by [KarmiApi] on HTTP 401.
  void expire() {
    if (isSignedIn) _end(SessionEnd.expired);
  }

  Future<void> _end(SessionEnd reason) async {
    api.token = null;
    _lastEnd = reason;
    notifyListeners();
    await _prefs.remove(_key);
  }
}
