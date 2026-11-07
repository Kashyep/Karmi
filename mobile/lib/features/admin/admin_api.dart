/// Admin API contract (`/v1/admin/*`, served by src/daily_agent/routes/admin.py).
///
/// UI and controllers depend only on [AdminApi]; tests use fakes. The HTTP
/// implementation lives in `admin_http_api.dart`.
library;

import 'dart:convert';
import 'dart:typed_data';

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

/// Why an [AdminFailure] happened; drives the error copy.
enum AdminFailureKind {
  /// Transport failed before any response (no connection, reset, stale socket).
  network,

  /// No response within the per-attempt timeout.
  timeout,

  /// Server answered with a non-2xx status; [AdminFailure.statusCode] is set.
  server,

  /// Server answered 2xx but the body was not the expected shape.
  badResponse,

  /// Anything else; generic copy.
  other,
}

/// Any other failure (network, 5xx, 404, 4xx validation, bad body).
final class AdminFailure extends AdminException {
  /// A [statusCode] means an HTTP status failure ([AdminFailureKind.server]).
  const AdminFailure([this.statusCode])
    : kind = statusCode == null
          ? AdminFailureKind.other
          : AdminFailureKind.server;
  const AdminFailure.network()
    : statusCode = null,
      kind = AdminFailureKind.network;
  const AdminFailure.timeout()
    : statusCode = null,
      kind = AdminFailureKind.timeout;
  const AdminFailure.badResponse([this.statusCode])
    : kind = AdminFailureKind.badResponse;

  final int? statusCode;
  final AdminFailureKind kind;
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
    this.openBugReports = 0,
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
    openBugReports: (j['open_bug_reports'] as num?)?.toInt() ?? 0,
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
  final int openBugReports;
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
    this.monthSpendInr,
    this.creditsRemaining,
    this.sessions,
  });
  factory AdminUsage.fromJson(Map<String, dynamic> j) => AdminUsage(
    todayRequests: (j['today_requests'] as num?)?.toInt(),
    monthSpendInr: (j['month_spend_inr'] as num?)?.toDouble(),
    creditsRemaining: (j['credits_remaining'] as num?)?.toDouble(),
    sessions: (j['sessions'] as num?)?.toInt(),
  );
  // Null means the server did not report the value; UI shows "Unavailable".
  final int? todayRequests;
  final double? monthSpendInr;
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

class ModelHealth {
  const ModelHealth({
    required this.model,
    required this.provider,
    this.lastSuccessAt,
    this.errorRate,
    this.p50LatencyMs,
    this.runs = 0,
  });

  factory ModelHealth.fromJson(Map<String, dynamic> j) => ModelHealth(
    model: j['model'] as String? ?? '',
    provider: j['provider'] as String? ?? '',
    lastSuccessAt: _date(j['last_success_at']),
    errorRate: (j['error_rate'] as num?)?.toDouble(),
    p50LatencyMs: (j['p50_latency_ms'] as num?)?.toDouble(),
    runs: (j['runs'] as num?)?.toInt() ?? 0,
  );

  final String model;
  final String provider;
  final DateTime? lastSuccessAt;
  final double? errorRate;
  final double? p50LatencyMs;
  final int runs;
}

class AdminMonitor {
  const AdminMonitor({
    this.activeUsers,
    this.activeStreams,
    this.reqPerMin,
    this.errorRate,
    this.p95LatencyMs,
    this.spendTodayInr,
    this.platformBudgetInr,
    this.costTodayInr,
    this.requestsToday,
    this.dailyRequestCap,
    this.successRate,
    this.openBugReports,
    this.modelHealth = const [],
    this.providerHealth = const [],
    this.generatedAt,
  });
  factory AdminMonitor.fromJson(Map<String, dynamic> j) => AdminMonitor(
    activeUsers: (j['active_users'] as num?)?.toInt(),
    activeStreams: (j['active_streams'] as num?)?.toInt(),
    reqPerMin: (j['req_per_min'] as num?)?.toDouble(),
    errorRate: (j['error_rate'] as num?)?.toDouble(),
    p95LatencyMs: (j['p95_latency_ms'] as num?)?.toDouble(),
    spendTodayInr: (j['spend_today_inr'] as num?)?.toDouble(),
    platformBudgetInr: (j['platform_budget_inr'] as num?)?.toDouble(),
    costTodayInr: (j['cost_today_inr'] as num?)?.toDouble(),
    requestsToday: (j['requests_today'] as num?)?.toInt(),
    dailyRequestCap: (j['daily_request_cap'] as num?)?.toInt(),
    successRate: (j['success_rate'] as num?)?.toDouble(),
    openBugReports: (j['open_bug_reports'] as num?)?.toInt(),
    modelHealth: [
      for (final e in (j['model_health'] as List<dynamic>? ?? const []))
        if (e is Map<String, dynamic>) ModelHealth.fromJson(e),
    ],
    providerHealth: [
      for (final e in (j['provider_health'] as List<dynamic>? ?? const []))
        if (e is Map<String, dynamic>)
          ProviderHealth(
            provider: e['provider'] as String? ?? '',
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
  final double? spendTodayInr;
  final double? platformBudgetInr;
  final double? costTodayInr;
  final int? requestsToday;
  final int? dailyRequestCap;
  final double? successRate;
  final int? openBugReports;
  final List<ModelHealth> modelHealth;
  final List<ProviderHealth> providerHealth;
  final DateTime? generatedAt;
}

const List<String> kBugReportCategories = [
  'crash',
  'chat',
  'ui',
  'account',
  'other',
];

const Set<String> kAllowedBugReportStatuses = {
  'new',
  'triaged',
  'in_progress',
  'fixed',
  'closed',
  'duplicate',
  'wontfix',
};

const Map<String, Set<String>> kAllowedBugReportTransitions = {
  'new': {'triaged', 'duplicate', 'wontfix', 'closed'},
  'triaged': {'in_progress', 'duplicate', 'wontfix', 'closed'},
  'in_progress': {'fixed', 'wontfix', 'closed'},
  'fixed': {'closed', 'in_progress'},
  'duplicate': {'closed', 'triaged'},
  'wontfix': {'closed', 'triaged'},
  'closed': {'triaged'},
};

String bugReportStatusLabel(String status) => switch (status) {
  'new' => 'New',
  'triaged' => 'Triaged',
  'in_progress' => 'In progress',
  'fixed' => 'Fixed',
  'closed' => 'Closed',
  'duplicate' => 'Duplicate',
  'wontfix' => "Won't fix",
  _ => status,
};

String bugReportCategoryLabel(String category) => switch (category) {
  'crash' => 'Crash',
  'chat' => 'Chat',
  'ui' => 'UI',
  'account' => 'Account',
  'other' => 'Other',
  _ => category,
};

class AdminBugReportItem {
  const AdminBugReportItem({
    required this.id,
    required this.ticket,
    required this.category,
    required this.status,
    required this.descriptionPreview,
    this.userId,
    this.userDisplayName,
    this.hasScreenshot = false,
    this.createdAt,
    this.updatedAt,
  });

  factory AdminBugReportItem.fromJson(Map<String, dynamic> j) =>
      AdminBugReportItem(
        id: j['id'] as String? ?? '',
        ticket: j['ticket'] as String? ?? '',
        category: j['category'] as String? ?? '',
        status: j['status'] as String? ?? '',
        descriptionPreview: j['description_preview'] as String? ?? '',
        userId: j['user_id'] as String?,
        userDisplayName: j['user_display_name'] as String?,
        hasScreenshot: j['has_screenshot'] as bool? ?? false,
        createdAt: _date(j['created_at']),
        updatedAt: _date(j['updated_at']),
      );

  final String id;
  final String ticket;
  final String category;
  final String status;
  final String descriptionPreview;
  final String? userId;
  final String? userDisplayName;
  final bool hasScreenshot;
  final DateTime? createdAt;
  final DateTime? updatedAt;
}

class AdminBugReportPage {
  const AdminBugReportPage({required this.items, this.nextCursor});

  factory AdminBugReportPage.fromJson(Map<String, dynamic> j) =>
      AdminBugReportPage(
        items: [
          for (final e in (j['items'] as List<dynamic>? ?? const []))
            if (e is Map<String, dynamic>) AdminBugReportItem.fromJson(e),
        ],
        nextCursor: j['next_cursor'] as String?,
      );

  final List<AdminBugReportItem> items;
  final String? nextCursor;
}

class AdminBugReportUser {
  const AdminBugReportUser({
    required this.id,
    required this.displayName,
    this.plan,
  });

  factory AdminBugReportUser.fromJson(Map<String, dynamic> j) =>
      AdminBugReportUser(
        id: j['id'] as String? ?? '',
        displayName: j['display_name'] as String? ?? '',
        plan: j['plan'] as String?,
      );

  final String id;
  final String displayName;
  final String? plan;
}

class AdminBugReportDetail {
  const AdminBugReportDetail({
    required this.id,
    required this.ticket,
    required this.category,
    required this.description,
    required this.diagnostics,
    required this.status,
    this.adminNotes,
    this.hasScreenshot = false,
    this.user,
    this.createdAt,
    this.updatedAt,
    this.triagedAt,
    this.resolvedAt,
  });

  factory AdminBugReportDetail.fromJson(Map<String, dynamic> j) {
    final userJson = j['user'] as Map<String, dynamic>?;
    final diag = j['diagnostics'];
    return AdminBugReportDetail(
      id: j['id'] as String? ?? '',
      ticket: j['ticket'] as String? ?? '',
      category: j['category'] as String? ?? '',
      description: j['description'] as String? ?? '',
      diagnostics: diag is Map<String, dynamic> ? diag : const {},
      status: j['status'] as String? ?? '',
      adminNotes: j['admin_notes'] as String?,
      hasScreenshot: j['has_screenshot'] as bool? ?? false,
      user: userJson != null ? AdminBugReportUser.fromJson(userJson) : null,
      createdAt: _date(j['created_at']),
      updatedAt: _date(j['updated_at']),
      triagedAt: _date(j['triaged_at']),
      resolvedAt: _date(j['resolved_at']),
    );
  }

  final String id;
  final String ticket;
  final String category;
  final String description;
  final Map<String, dynamic> diagnostics;
  final String status;
  final String? adminNotes;
  final bool hasScreenshot;
  final AdminBugReportUser? user;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? triagedAt;
  final DateTime? resolvedAt;
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
String? _text(Object? v) =>
    v == null ? null : (v is String ? v : jsonEncode(v));

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

  /// Exactly one of [deltaInr] / [budgetInr] is non-null.
  Future<void> adjustCredits(
    String token,
    String id, {
    double? deltaInr,
    double? budgetInr,
    required String reason,
  });

  /// `GET /users/{id}/export` with `X-Admin-Reason: ...`; returns the pretty-printed JSON text.
  /// [reason] is mandatory (private-data access is audited).
  Future<String> exportUser(String token, String id, {required String reason});

  /// `DELETE /users/{id}` with `{reason, confirm: "DELETE"}`.
  Future<void> deleteUser(String token, String id, {required String reason});

  Future<AdminMonitor> monitor(String token);
  Future<AuditPage> audit(String token, {int limit = 50, String? cursor});

  Future<AdminBugReportPage> listBugReports(
    String token, {
    String? status,
    String? category,
    int limit = 25,
    String? cursor,
  });
  Future<AdminBugReportDetail> getBugReport(String token, String id);
  Future<Uint8List> getBugReportScreenshot(String token, String id);
  Future<AdminBugReportDetail> patchBugReport(
    String token,
    String id, {
    String? status,
    String? adminNotes,
    required String reason,
  });
}
