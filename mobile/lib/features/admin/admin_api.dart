/// Admin API contract (`/v1/admin/*`, served by src/daily_agent/routes/admin.py).
///
/// UI and controllers depend only on [AdminApi]; tests use fakes. The HTTP
/// implementation lives in `admin_http_api.dart`.
library;

import 'dart:convert';

/// Thrown for admin-specific failures. Screens map these to copy.
sealed class AdminException implements Exception {
  const AdminException();
}

/// 403: caller is not an allow-listed admin. Hides every admin entry point.
final class AdminForbidden extends AdminException {
  const AdminForbidden();
}

/// 401 from `/admin/session` (wrong code) or an expired/missing X-Admin-Session.
final class AdminUnauthorized extends AdminException {
  const AdminUnauthorized();
}

/// 423: too many wrong codes; try again after [retryAfter].
final class AdminLockedOut extends AdminException {
  const AdminLockedOut(this.retryAfter);
  final Duration retryAfter;
}

/// Any other failure (network, 5xx, 404, 4xx validation, bad body).
final class AdminFailure extends AdminException {
  const AdminFailure([this.statusCode]);
  final int? statusCode;
}

class AdminSessionGrant {
  const AdminSessionGrant({required this.token, required this.expiresAt});
  final String token;
  final DateTime expiresAt;
}

class AdminUser {
  const AdminUser({
    required this.id,
    required this.email,
    required this.displayName,
    required this.tier,
    required this.disabled,
    this.tester = false,
    this.testerLabel,
    this.adminNotes,
    this.effectivePlan,
    this.planExpiresAt,
    this.revertPlanId,
    this.createdAt,
    this.lastActiveAt,
  });

  factory AdminUser.fromJson(Map<String, dynamic> j) => AdminUser(
    id: j['id'] as String,
    email: j['email'] as String? ?? '',
    displayName: j['display_name'] as String? ?? '',
    tier: j['tier']?.toString() ?? '',
    disabled: j['disabled'] as bool? ?? false,
    tester: j['tester'] as bool? ?? false,
    testerLabel: j['tester_label'] as String?,
    adminNotes: j['admin_notes'] as String?,
    effectivePlan: j['effective_plan'] as String?,
    planExpiresAt: _date(j['plan_expires_at']),
    revertPlanId: j['revert_plan_id']?.toString(),
    createdAt: _date(j['created_at']),
    lastActiveAt: _date(j['last_active_at']),
  );

  final String id;
  final String email;
  final String displayName;
  final String tier;
  final bool disabled;
  final bool tester;
  final String? testerLabel;
  final String? adminNotes;
  final String? effectivePlan;
  final DateTime? planExpiresAt;
  final String? revertPlanId;
  final DateTime? createdAt;
  final DateTime? lastActiveAt;
}

class AdminUserPage {
  const AdminUserPage({required this.items, this.nextCursor});
  factory AdminUserPage.fromJson(Map<String, dynamic> j) => AdminUserPage(
    items: [
      for (final e in (j['items'] as List<dynamic>? ?? const []))
        AdminUser.fromJson(e as Map<String, dynamic>),
    ],
    nextCursor: j['next_cursor'] as String?,
  );
  final List<AdminUser> items;
  final String? nextCursor;
}

class AdminUsage {
  const AdminUsage({
    this.todayRequests,
    this.monthSpendUsd,
    this.creditsRemaining,
    this.sessions,
  });
  factory AdminUsage.fromJson(Map<String, dynamic> j) => AdminUsage(
    todayRequests: (j['today_requests'] as num?)?.toInt(),
    monthSpendUsd: (j['month_spend_usd'] as num?)?.toDouble(),
    creditsRemaining: (j['credits_remaining'] as num?)?.toDouble(),
    sessions: (j['sessions'] as num?)?.toInt(),
  );
  // Null means the server did not report the value; UI shows "Unavailable".
  final int? todayRequests;
  final double? monthSpendUsd;
  final double? creditsRemaining;
  final int? sessions;
}

class AdminUserDetail {
  const AdminUserDetail({required this.user, required this.usage});

  /// Detail JSON is the user object plus a nested `usage` object.
  factory AdminUserDetail.fromJson(Map<String, dynamic> j) => AdminUserDetail(
    user: AdminUser.fromJson(j),
    usage: AdminUsage.fromJson(
      (j['usage'] as Map<String, dynamic>?) ?? const {},
    ),
  );
  final AdminUser user;
  final AdminUsage usage;
}

class ProviderHealth {
  const ProviderHealth({required this.provider, required this.status});
  final String provider;
  final String status;
}

class AdminMonitor {
  const AdminMonitor({
    this.activeUsers,
    this.activeStreams,
    this.reqPerMin,
    this.errorRate,
    this.p95LatencyMs,
    this.spendTodayUsd,
    this.platformBudgetUsd,
    this.providerHealth = const [],
    this.generatedAt,
  });
  factory AdminMonitor.fromJson(Map<String, dynamic> j) => AdminMonitor(
    activeUsers: (j['active_users'] as num?)?.toInt(),
    activeStreams: (j['active_streams'] as num?)?.toInt(),
    reqPerMin: (j['req_per_min'] as num?)?.toDouble(),
    errorRate: (j['error_rate'] as num?)?.toDouble(),
    p95LatencyMs: (j['p95_latency_ms'] as num?)?.toDouble(),
    spendTodayUsd: (j['spend_today_usd'] as num?)?.toDouble(),
    platformBudgetUsd: (j['platform_budget_usd'] as num?)?.toDouble(),
    providerHealth: [
      for (final e in (j['provider_health'] as List<dynamic>? ?? const []))
        ProviderHealth(
          provider: (e as Map<String, dynamic>)['provider'] as String? ?? '',
          status: e['status'] as String? ?? 'unknown',
        ),
    ],
    generatedAt: _date(j['generated_at']),
  );
  final int? activeUsers;
  final int? activeStreams;
  final double? reqPerMin;
  final double? errorRate; // fraction 0..1
  final double? p95LatencyMs;
  final double? spendTodayUsd;
  final double? platformBudgetUsd;
  final List<ProviderHealth> providerHealth;
  final DateTime? generatedAt;
}

class AuditEntry {
  const AuditEntry({
    required this.id,
    required this.action,
    this.at,
    this.adminUserId,
    this.targetUserId,
    this.reason,
    this.detail,
  });
  factory AuditEntry.fromJson(Map<String, dynamic> j) => AuditEntry(
    id: j['id'].toString(),
    at: _date(j['at']),
    adminUserId: j['admin_user_id'] as String?,
    action: j['action'] as String? ?? '',
    targetUserId: j['target_user_id'] as String?,
    reason: j['reason'] as String?,
    detail: _text(j['detail']),
  );
  final String id;
  final DateTime? at;
  final String? adminUserId;
  final String action;
  final String? targetUserId;
  final String? reason;
  final String? detail;
}

class AuditPage {
  const AuditPage({required this.items, this.nextCursor});
  factory AuditPage.fromJson(Map<String, dynamic> j) => AuditPage(
    items: [
      for (final e in (j['items'] as List<dynamic>? ?? const []))
        AuditEntry.fromJson(e as Map<String, dynamic>),
    ],
    nextCursor: j['next_cursor'] as String?,
  );
  final List<AuditEntry> items;
  final String? nextCursor;
}

DateTime? _date(Object? v) => v is String ? DateTime.tryParse(v) : null;

/// Free-form server values (audit `detail` is a JSON object) shown as text.
String? _text(Object? v) => v == null ? null : (v is String ? v : jsonEncode(v));

/// All calls (except [openSession]/[probe]) send the in-memory admin token as
/// `X-Admin-Session`. Every mutation requires a non-empty [reason].
abstract class AdminApi {
  /// `GET /v1/admin/session` with no admin token: throws [AdminForbidden] for
  /// non-admins; returns normally for eligible admins. Used only to decide
  /// whether to show the admin entry.
  Future<void> probe();

  /// `POST /v1/admin/session {code}`.
  Future<AdminSessionGrant> openSession(String code);

  /// `DELETE /v1/admin/session`.
  Future<void> closeSession(String token);

  Future<AdminUserPage> listUsers(
    String token, {
    String? q,
    String? tier,
    String? status,
    String? testerLabel,
    bool? suspended,
    DateTime? planExpiringBefore,
    int limit = 25,
    String? cursor,
  });
  Future<AdminUserDetail> getUser(String token, String id);
  Future<void> suspend(String token, String id, {required String reason});
  Future<void> unsuspend(String token, String id, {required String reason});
  Future<void> revokeSessions(
    String token,
    String id, {
    required String reason,
  });
  Future<void> editUser(
    String token,
    String id, {
    String? displayName,
    bool? tester,
    String? testerLabel,
    String? adminNotes,
    required String reason,
  });
  Future<void> changeTier(
    String token,
    String id, {
    required String tier,
    required String reason,
    DateTime? expiresAt,
  });
  Future<void> bulkTier(
    String token,
    List<String> userIds, {
    required String tier,
    required String reason,
    DateTime? expiresAt,
  });

  /// Exactly one of [deltaUsd] / [budgetUsd] is non-null.
  Future<void> adjustCredits(
    String token,
    String id, {
    double? deltaUsd,
    double? budgetUsd,
    required String reason,
  });

  /// `GET /users/{id}/export?reason=...`; returns the pretty-printed JSON text.
  /// [reason] is mandatory (private-data access is audited).
  Future<String> exportUser(String token, String id, {required String reason});

  /// `DELETE /users/{id}` with `{reason, confirm: "DELETE"}`.
  Future<void> deleteUser(String token, String id, {required String reason});

  Future<AdminMonitor> monitor(String token);
  Future<AuditPage> audit(String token, {int limit = 50, String? cursor});
}
