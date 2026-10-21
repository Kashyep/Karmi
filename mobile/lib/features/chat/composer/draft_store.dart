import 'package:shared_preferences/shared_preferences.dart';

abstract class DraftStore {
  Future<String?> load(String key);
  Future<void> save(String key, String text);
  Future<void> clear(String key);
}

/// Process-lifetime drafts for when no user identity is known yet. Never
/// written to disk, so it cannot leak into another user's session.
class MemoryDraftStore implements DraftStore {
  final Map<String, String> _drafts = {};

  @override
  Future<String?> load(String key) async => _drafts[key];

  @override
  Future<void> save(String key, String text) async => _drafts[key] = text;

  @override
  Future<void> clear(String key) async => _drafts.remove(key);
}

/// Persists drafts under `draft.v1.<userId>.<key>` so two users on one device
/// never see each other's drafts.
class SharedPrefsDraftStore implements DraftStore {
  SharedPrefsDraftStore({required this.userId, SharedPreferences? prefs})
    : assert(userId.isNotEmpty && !userId.contains('.')),
      _prefs = prefs;

  static const _prefix = 'draft.v1.';

  final String userId;
  final SharedPreferences? _prefs;

  static String storageKey(String userId, String key) =>
      '$_prefix$userId.$key';

  Future<SharedPreferences> _getPrefs() async =>
      _prefs ?? await SharedPreferences.getInstance();

  @override
  Future<String?> load(String key) async {
    final sp = await _getPrefs();
    return sp.getString(storageKey(userId, key));
  }

  @override
  Future<void> save(String key, String text) async {
    final sp = await _getPrefs();
    await sp.setString(storageKey(userId, key), text);
  }

  @override
  Future<void> clear(String key) async {
    final sp = await _getPrefs();
    await sp.remove(storageKey(userId, key));
  }

  /// Clears every stored draft for every user (sign-out).
  static Future<void> clearAllDrafts([SharedPreferences? prefs]) async {
    final sp = prefs ?? await SharedPreferences.getInstance();
    final keys = sp.getKeys().where((k) => k.startsWith(_prefix)).toList();
    for (final k in keys) {
      await sp.remove(k);
    }
  }

  /// Removes pre-scoping drafts (`draft.v1.<key>`, no user segment). Their
  /// owner is unknown, so they are discarded rather than shown to anyone.
  /// Scoped keys always contain a '.' after the prefix.
  static Future<void> purgeUnscopedDrafts([SharedPreferences? prefs]) async {
    final sp = prefs ?? await SharedPreferences.getInstance();
    final keys = sp
        .getKeys()
        .where((k) => k.startsWith(_prefix))
        .where((k) => !k.substring(_prefix.length).contains('.'))
        .toList();
    for (final k in keys) {
      await sp.remove(k);
    }
  }
}
