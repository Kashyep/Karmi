import 'package:shared_preferences/shared_preferences.dart';

abstract class DraftStore {
  Future<String?> load(String key);
  Future<void> save(String key, String text);
  Future<void> clear(String key);
}

class SharedPrefsDraftStore implements DraftStore {
  const SharedPrefsDraftStore({SharedPreferences? prefs}) : _prefs = prefs;

  final SharedPreferences? _prefs;

  static String storageKey(String key) => 'draft.v1.$key';

  Future<SharedPreferences> _getPrefs() async =>
      _prefs ?? await SharedPreferences.getInstance();

  @override
  Future<String?> load(String key) async {
    final sp = await _getPrefs();
    return sp.getString(storageKey(key));
  }

  @override
  Future<void> save(String key, String text) async {
    final sp = await _getPrefs();
    await sp.setString(storageKey(key), text);
  }

  @override
  Future<void> clear(String key) async {
    final sp = await _getPrefs();
    await sp.remove(storageKey(key));
  }
}
