import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:clerk_flutter/clerk_flutter.dart';

import '../api/karmi_api.dart';
import '../features/chat/composer/draft_store.dart';
import '../features/bug_report/bug_report_queue.dart';

/// `--dart-define=KARMI_DEV_AUTH=false` hides the local development sign-in.
/// Defaults on outside release mode.
const bool kDevAuthEnabled = bool.fromEnvironment(
  'KARMI_DEV_AUTH',
  defaultValue: !kReleaseMode,
);

enum SessionEnd { none, signedOut, expired }

/// Adapts Clerk's persisted session (production) and `/dev/token` (local dev)
/// to the app's signed-in state. Clerk tokens are requested per API call and
/// are never copied into SharedPreferences.
class KarmiSession extends ChangeNotifier {
  KarmiSession({
    required this.api,
    required SharedPreferences prefs,
    this.clerkAuth,
  }) : _prefs = prefs {
    unawaited(SharedPrefsDraftStore.purgeUnscopedDrafts(prefs));
    final auth = clerkAuth;
    if (auth != null) {
      // Never let a leftover synthetic token authenticate a Clerk-configured
      // build, including when Clerk currently has no active session.
      api.token = null;
      unawaited(_prefs.remove(_key));
      api.tokenProvider = _clerkToken;
      auth.addListener(_onClerkChange);
      _wasClerkSignedIn = auth.isSignedIn;
      if (auth.isSignedIn) {
        _lastSignedInUserId = auth.user?.id;
      }
    } else {
      api.token = _prefs.getString(_key);
      final token = api.token;
      if (token != null) {
        final sep = token.indexOf('|');
        if (sep > 0) {
          _lastSignedInUserId = token.substring(0, sep);
        }
      }
    }
    api.onUnauthorized = expire;
  }

  static const _key = 'dev_session_token';

  final KarmiApi api;
  final SharedPreferences _prefs;
  final ClerkAuthState? clerkAuth;
  SessionEnd _lastEnd = SessionEnd.none;
  bool _wasClerkSignedIn = false;
  String? _lastSignedInUserId;
  bool get isSignedIn => api.token != null || clerkAuth?.isSignedIn == true;

  bool get hasClerk => clerkAuth != null;

  /// Why the previous session ended, for the Welcome screen copy.
  SessionEnd get lastEnd => _lastEnd;

  /// Stable id of the signed-in user, or null while unknown (e.g. Clerk still
  /// loading). Dev tokens are `<userId>|<role>|<exp>|<tv>|<sig>`.
  String? get userId {
    final auth = clerkAuth;
    final String? uid;
    if (auth != null) {
      uid = auth.user?.id;
    } else {
      final token = api.token;
      if (token == null) {
        uid = null;
      } else {
        final sep = token.indexOf('|');
        uid = sep > 0 ? token.substring(0, sep) : null;
      }
    }
    if (uid != null && uid.isNotEmpty) {
      _lastSignedInUserId = uid;
    }
    return uid;
  }

  /// Drafts scoped to the signed-in user; null when no user id is known, in
  /// which case callers fall back to non-persistent drafts.
  SharedPrefsDraftStore? get draftStore {
    final uid = userId;
    if (uid == null || uid.isEmpty || uid.contains('.')) return null;
    return SharedPrefsDraftStore(userId: uid, prefs: _prefs);
  }

  Future<String?> _clerkToken() async {
    final auth = clerkAuth;
    if (auth == null || !auth.isSignedIn) return null;
    return (await auth.sessionToken()).jwt;
  }

  void _onClerkChange() {
    final signedIn = clerkAuth?.isSignedIn == true;
    if (_wasClerkSignedIn && !signedIn) {
      final oldUserId = userId ?? _lastSignedInUserId;
      if (_lastEnd != SessionEnd.expired) {
        _lastEnd = SessionEnd.signedOut;
      }
      unawaited(SharedPrefsDraftStore.clearAllDrafts(_prefs));
      if (_lastEnd == SessionEnd.signedOut &&
          oldUserId != null &&
          oldUserId.isNotEmpty) {
        unawaited(BugReportQueue(prefs: _prefs).clearUserItems(oldUserId));
      }
      if (_lastEnd == SessionEnd.signedOut) {
        _lastSignedInUserId = null;
      }
    } else if (signedIn) {
      if (!_wasClerkSignedIn) {
        _lastEnd = SessionEnd.none;
      }
      final currentUid = clerkAuth?.user?.id;
      if (currentUid != null && currentUid.isNotEmpty) {
        _lastSignedInUserId = currentUid;
      }
    }
    _wasClerkSignedIn = signedIn;
    notifyListeners();
  }

  /// Throws [KarmiApiException] on failure; the token is unchanged then.
  Future<void> signInWithDevToken() async {
    final token = await api.issueDevToken();
    api.token = token;
    final sep = token.indexOf('|');
    if (sep > 0) {
      _lastSignedInUserId = token.substring(0, sep);
    }
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
    final oldUserId = userId ?? _lastSignedInUserId;
    api.token = null;
    _lastEnd = reason;
    notifyListeners();
    await _prefs.remove(_key);
    await SharedPrefsDraftStore.clearAllDrafts(_prefs);
    if (reason == SessionEnd.signedOut) {
      if (oldUserId != null && oldUserId.isNotEmpty) {
        await BugReportQueue(prefs: _prefs).clearUserItems(oldUserId);
      }
      _lastSignedInUserId = null;
    }
    if (clerkAuth?.isSignedIn == true) {
      await clerkAuth!.signOut();
    }
  }

  @override
  void dispose() {
    clerkAuth?.removeListener(_onClerkChange);
    super.dispose();
  }
}
