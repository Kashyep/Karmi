import 'dart:convert';
import 'dart:typed_data';

import 'package:karmi_app/features/admin/admin_api.dart';

/// In-memory [AdminApi] for controller and widget tests.
///
/// * [calls] records every call as `name:arg:...` strings, e.g.
///   `suspend:u1:spam`, `tier:u1:pro:support`, `open:123456`.
/// * [failNext] is thrown by the next call (then cleared).
/// * [forbidden] makes [probe] and [openSession] throw [AdminForbidden].
/// * [code] is the only accepted code; anything else throws
///   [AdminUnauthorized], or [AdminLockedOut] when [lockedOut] is set.
class FakeAdminApi implements AdminApi {
  FakeAdminApi({
    List<AdminUser>? users,
    this.forbidden = false,
    this.code = '123456',
    this.sessionTtl = const Duration(minutes: 15),
    List<AdminBugReportDetail>? bugReports,
  }) : users = users ?? _defaultUsers() {
    if (bugReports != null) {
      this.bugReports.addAll(bugReports);
    }
  }

  final List<String> calls = [];
  final List<AdminUser> users;
  bool forbidden;
  final String code;
  final Duration sessionTtl;

  /// When non-null, [openSession] throws [AdminLockedOut] with this value.
  Duration? lockedOut;

  /// Thrown by the next call, then cleared.
  AdminException? failNext;

  AdminMonitor monitorValue = const AdminMonitor(
    activeUsers: 4,
    activeStreams: 2,
    reqPerMin: 12.5,
    errorRate: 0.02,
    p95LatencyMs: 840,
    spendTodayInr: 3.25,
    platformBudgetInr: 50,
    costTodayInr: 3.25,
    requestsToday: 120,
    dailyRequestCap: 1000,
    successRate: 0.98,
    openBugReports: 1,
    modelHealth: [
      ModelHealth(
        model: 'claude-3-5-sonnet',
        provider: 'anthropic',
        errorRate: 0.01,
        p50LatencyMs: 650,
        runs: 50,
      ),
    ],
    providerHealth: [
      ProviderHealth(provider: 'anthropic', status: 'ok'),
      ProviderHealth(provider: 'openai', status: 'degraded'),
    ],
  );

  final List<AdminBugReportDetail> bugReports = [];
  final Map<String, Uint8List> bugReportScreenshots = {};

  int _tokenSeq = 0;

  /// Sets how many users one [listUsers] page returns.
  int pageSize = 25;

  void _record(String call) => calls.add(call);

  void _maybeFail() {
    final e = failNext;
    if (e != null) {
      failNext = null;
      throw e;
    }
  }

  static List<AdminUser> _defaultUsers() => [
    AdminUser(
      id: 'u1',
      email: 'ada@example.com',
      displayName: 'Ada',
      tier: 'ananta',
      disabled: false,
      createdAt: DateTime.utc(2026, 1, 2),
      lastActiveAt: DateTime.utc(2026, 10, 1),
    ),
    const AdminUser(
      id: 'u2',
      email: 'bob@example.com',
      displayName: 'Bob',
      tier: 'yanta',
      disabled: true,
    ),
  ];

  AdminUser _find(String id) {
    for (final u in users) {
      if (u.id == id) return u;
    }
    throw const AdminFailure(404);
  }

  void _replace(AdminUser updated) {
    final i = users.indexWhere((u) => u.id == updated.id);
    if (i >= 0) users[i] = updated;
  }

  @override
  Future<void> probe() async {
    _record('probe');
    _maybeFail();
    if (forbidden) throw const AdminForbidden();
  }

  @override
  Future<AdminSessionGrant> openSession(String code) async {
    _record('open:$code');
    _maybeFail();
    if (forbidden) throw const AdminForbidden();
    final wait = lockedOut;
    if (wait != null) throw AdminLockedOut(wait);
    if (code != this.code) throw const AdminUnauthorized();
    _tokenSeq++;
    return AdminSessionGrant(
      token: 'tok-$_tokenSeq',
      expiresAt: DateTime.now().add(sessionTtl),
    );
  }

  @override
  Future<void> closeSession(String token) async {
    _record('close:$token');
    _maybeFail();
  }

  @override
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
  }) async {
    _record(
      'list:${q ?? ''}:${tier ?? ''}:${status ?? ''}:${testerLabel ?? ''}:${cursor ?? ''}',
    );
    _maybeFail();
    final filtered = users.where((u) {
      if (q != null && q.isNotEmpty) {
        final needle = q.toLowerCase();
        if (!u.email.toLowerCase().contains(needle) &&
            !u.displayName.toLowerCase().contains(needle)) {
          return false;
        }
      }
      if (tier != null && tier.isNotEmpty && u.tier != tier) return false;
      if (testerLabel != null &&
          testerLabel.isNotEmpty &&
          u.testerLabel != testerLabel) {
        return false;
      }
      if (suspended != null && u.disabled != suspended) return false;
      if (status == 'active' && u.disabled) return false;
      if (status == 'suspended' && !u.disabled) return false;
      if (planExpiringBefore != null &&
          (u.planExpiresAt == null ||
              !u.planExpiresAt!.isBefore(planExpiringBefore))) {
        return false;
      }
      return true;
    }).toList();
    final start = int.tryParse(cursor ?? '') ?? 0;
    final size = limit < pageSize ? limit : pageSize;
    final end = (start + size) < filtered.length
        ? start + size
        : filtered.length;
    return AdminUserPage(
      items: filtered.sublist(start.clamp(0, filtered.length), end),
      nextCursor: end < filtered.length ? '$end' : null,
    );
  }

  @override
  Future<AdminUserDetail> getUser(String token, String id) async {
    _record('get:$id');
    _maybeFail();
    return AdminUserDetail(
      user: _find(id),
      usage: const AdminUsage(
        todayRequests: 7,
        monthSpendInr: 1.5,
        creditsRemaining: 10,
        sessions: 1,
      ),
    );
  }

  @override
  Future<void> suspend(
    String token,
    String id, {
    required String reason,
  }) async {
    _record('suspend:$id:$reason');
    _maybeFail();
    final u = _find(id);
    _replace(_copy(u, disabled: true));
  }

  @override
  Future<void> unsuspend(
    String token,
    String id, {
    required String reason,
  }) async {
    _record('unsuspend:$id:$reason');
    _maybeFail();
    final u = _find(id);
    _replace(_copy(u, disabled: false));
  }

  @override
  Future<void> revokeSessions(
    String token,
    String id, {
    required String reason,
  }) async {
    _record('revoke:$id:$reason');
    _maybeFail();
    _find(id);
  }

  @override
  Future<void> editUser(
    String token,
    String id, {
    String? displayName,
    bool? tester,
    String? testerLabel,
    String? adminNotes,
    required String reason,
  }) async {
    _record('edit:$id:$reason');
    _maybeFail();
    final u = _find(id);
    _replace(
      _copy(
        u,
        displayName: displayName,
        tester: tester,
        testerLabel: testerLabel,
        adminNotes: adminNotes,
      ),
    );
  }

  @override
  Future<void> changeTier(
    String token,
    String id, {
    required String tier,
    required String reason,
    DateTime? expiresAt,
  }) async {
    _record('tier:$id:$tier:${expiresAt?.toIso8601String() ?? ''}:$reason');
    _maybeFail();
    _replace(_copy(_find(id), tier: tier, planExpiresAt: expiresAt));
  }

  @override
  Future<void> bulkTier(
    String token,
    List<String> userIds, {
    required String tier,
    required String reason,
    DateTime? expiresAt,
  }) async {
    _record('bulk-tier:${userIds.join(',')}:$tier:$reason');
    _maybeFail();
    for (final id in userIds) {
      _replace(_copy(_find(id), tier: tier, planExpiresAt: expiresAt));
    }
  }

  @override
  Future<void> adjustCredits(
    String token,
    String id, {
    double? deltaInr,
    double? budgetInr,
    required String reason,
  }) async {
    _record(
      'credits:$id:delta=${deltaInr ?? ''}:budget=${budgetInr ?? ''}:$reason',
    );
    _maybeFail();
    _find(id);
  }

  @override
  Future<String> exportUser(
    String token,
    String id, {
    required String reason,
  }) async {
    _record('export:$id:$reason');
    _maybeFail();
    final u = _find(id);
    return const JsonEncoder.withIndent('  ').convert({
      'id': u.id,
      'email': u.email,
      'display_name': u.displayName,
      'tier': u.tier,
      'disabled': u.disabled,
    });
  }

  @override
  Future<void> deleteUser(
    String token,
    String id, {
    required String reason,
  }) async {
    _record('delete:$id:$reason');
    _maybeFail();
    _find(id);
    users.removeWhere((u) => u.id == id);
  }

  @override
  Future<AdminMonitor> monitor(String token) async {
    _record('monitor');
    _maybeFail();
    return monitorValue;
  }

  @override
  Future<AuditPage> audit(
    String token, {
    int limit = 50,
    String? cursor,
  }) async {
    _record('audit:${cursor ?? ''}');
    _maybeFail();
    return const AuditPage(items: []);
  }

  @override
  Future<AdminBugReportPage> listBugReports(
    String token, {
    String? status,
    String? category,
    int limit = 25,
    String? cursor,
  }) async {
    _record(
      'listBugReports:status=${status ?? ''}:category=${category ?? ''}:limit=$limit:cursor=${cursor ?? ''}',
    );
    _maybeFail();
    final filtered = bugReports.where((r) {
      if (status != null &&
          status.isNotEmpty &&
          status != 'all' &&
          r.status != status) {
        return false;
      }
      if (category != null &&
          category.isNotEmpty &&
          category != 'all' &&
          r.category != category) {
        return false;
      }
      return true;
    }).toList();
    final start = cursor == null ? 0 : int.tryParse(cursor) ?? 0;
    final effectiveLimit = pageSize < limit ? pageSize : limit;
    final end = (start + effectiveLimit).clamp(0, filtered.length);
    final page = start < filtered.length
        ? filtered.sublist(start, end)
        : <AdminBugReportDetail>[];
    return AdminBugReportPage(
      items: page
          .map(
            (r) => AdminBugReportItem(
              id: r.id,
              ticket: r.ticket,
              category: r.category,
              status: r.status,
              descriptionPreview: r.description.length > 140
                  ? r.description.substring(0, 140)
                  : r.description,
              userId: r.user?.id,
              userDisplayName: r.user?.displayName,
              hasScreenshot: r.hasScreenshot,
              createdAt: r.createdAt,
              updatedAt: r.updatedAt,
            ),
          )
          .toList(),
      nextCursor: end < filtered.length ? '$end' : null,
    );
  }

  @override
  Future<AdminBugReportDetail> getBugReport(String token, String id) async {
    _record('getBugReport:$id');
    _maybeFail();
    return bugReports.firstWhere(
      (b) => b.id == id,
      orElse: () => throw const AdminFailure(404),
    );
  }

  @override
  Future<Uint8List> getBugReportScreenshot(String token, String id) async {
    _record('getBugReportScreenshot:$id');
    _maybeFail();
    final bytes = bugReportScreenshots[id];
    if (bytes == null) throw const AdminFailure(404);
    return bytes;
  }

  @override
  Future<AdminBugReportDetail> patchBugReport(
    String token,
    String id, {
    String? status,
    String? adminNotes,
    required String reason,
  }) async {
    _record(
      'patchBugReport:$id:status=${status ?? ''}:adminNotes=${adminNotes ?? ''}:$reason',
    );
    _maybeFail();
    final index = bugReports.indexWhere((b) => b.id == id);
    if (index < 0) throw const AdminFailure(404);
    final current = bugReports[index];
    if (status != null && status != current.status) {
      final allowed = kAllowedBugReportTransitions[current.status] ?? const {};
      if (!allowed.contains(status)) {
        throw const AdminFailure(409);
      }
    }
    final updated = AdminBugReportDetail(
      id: current.id,
      ticket: current.ticket,
      category: current.category,
      description: current.description,
      diagnostics: current.diagnostics,
      status: status ?? current.status,
      adminNotes: adminNotes ?? current.adminNotes,
      hasScreenshot: current.hasScreenshot,
      user: current.user,
      createdAt: current.createdAt,
      updatedAt: DateTime.now(),
      triagedAt: status == 'triaged'
          ? (current.triagedAt ?? DateTime.now())
          : current.triagedAt,
      resolvedAt: {'fixed', 'closed', 'duplicate', 'wontfix'}.contains(status)
          ? (current.resolvedAt ?? DateTime.now())
          : current.resolvedAt,
    );
    bugReports[index] = updated;
    return updated;
  }

  static AdminUser _copy(
    AdminUser u, {
    bool? disabled,
    String? tier,
    String? displayName,
    bool? tester,
    String? testerLabel,
    String? adminNotes,
    DateTime? planExpiresAt,
  }) => AdminUser(
    id: u.id,
    email: u.email,
    displayName: displayName ?? u.displayName,
    tier: tier ?? u.tier,
    disabled: disabled ?? u.disabled,
    tester: tester ?? u.tester,
    testerLabel: testerLabel ?? u.testerLabel,
    adminNotes: adminNotes ?? u.adminNotes,
    effectivePlan: tier ?? u.effectivePlan,
    planExpiresAt: planExpiresAt ?? u.planExpiresAt,
    revertPlanId: u.revertPlanId,
    createdAt: u.createdAt,
    lastActiveAt: u.lastActiveAt,
    openBugReports: u.openBugReports,
  );
}
