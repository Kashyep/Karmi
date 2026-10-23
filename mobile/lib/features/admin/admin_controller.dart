import 'dart:async';

import 'package:flutter/foundation.dart';

import 'admin_api.dart';

enum AdminEligibility { unknown, notAdmin, eligible }

/// Holds admin eligibility and the in-memory admin session token. The token is
/// never persisted. When [isActive] the app shows ONLY the admin shell.
class AdminController extends ChangeNotifier {
  AdminController({required this.api, DateTime Function()? clock})
    : _now = clock ?? DateTime.now;

  final AdminApi api;
  final DateTime Function() _now;

  AdminEligibility _eligibility = AdminEligibility.unknown;
  String? _token;
  DateTime? _expiresAt;
  Timer? _expiry;

  AdminEligibility get eligibility => _eligibility;

  /// Show the "Admin console" entry only when true (probe did not get 403).
  bool get canEnter => _eligibility == AdminEligibility.eligible;

  String? get token => isActive ? _token : null;
  DateTime? get expiresAt => _expiresAt;
  bool get isActive =>
      _token != null && _expiresAt != null && _expiresAt!.isAfter(_now());

  /// Asks the server whether this account may use admin. 403 -> notAdmin;
  /// any other failure leaves the entry hidden (unknown) without surfacing.
  Future<void> probe() async {
    try {
      await api.probe();
      _eligibility = AdminEligibility.eligible;
    } on AdminForbidden {
      _eligibility = AdminEligibility.notAdmin;
    } on AdminException {
      _eligibility = AdminEligibility.unknown;
    }
    notifyListeners();
  }

  /// Throws [AdminUnauthorized] (wrong code), [AdminLockedOut], [AdminForbidden]
  /// (also marks the account notAdmin) or [AdminFailure].
  Future<void> verifyCode(String code) async {
    try {
      final grant = await api.openSession(code);
      _token = grant.token;
      _expiresAt = grant.expiresAt;
      _eligibility = AdminEligibility.eligible;
      _armExpiry();
    } on AdminForbidden {
      _eligibility = AdminEligibility.notAdmin;
      notifyListeners();
      rethrow;
    }
    notifyListeners();
  }

  /// Screens call this when any call throws [AdminUnauthorized] (expired).
  void sessionLost() {
    if (_token == null) return;
    _clear();
    notifyListeners();
  }

  /// Best-effort server logout, then always clears local state.
  Future<void> logout() async {
    final t = _token;
    _clear();
    notifyListeners();
    if (t != null) {
      try {
        await api.closeSession(t);
      } on AdminException {
        // Already cleared locally; the server session expires on its own.
      }
    }
  }

  /// Full reset on app sign-out.
  void reset() {
    _clear();
    _eligibility = AdminEligibility.unknown;
    notifyListeners();
  }

  void _armExpiry() {
    _expiry?.cancel();
    final left = _expiresAt!.difference(_now());
    _expiry = Timer(left.isNegative ? Duration.zero : left, sessionLost);
  }

  void _clear() {
    _expiry?.cancel();
    _expiry = null;
    _token = null;
    _expiresAt = null;
  }

  @override
  void dispose() {
    _expiry?.cancel();
    super.dispose();
  }
}
