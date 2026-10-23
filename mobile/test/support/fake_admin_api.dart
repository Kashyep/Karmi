import 'dart:convert';

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
  }) : users = users ?? _defaultUsers();

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
    spendTodayUsd: 3.25,
    platformBudgetUsd: 50,
    providerHealth: [
      ProviderHealth(provider: 'anthropic', status: 'ok'),
      ProviderHealth(provider: 'openai', status: 'degraded'),
    ],
  );

  int _tokenSeq = 0;
  int _pageSize = 25;

  /// Sets how many users one [listUsers] page returns.
  set pageSize(int v) => _pageSize = v;

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
            !u.displayName.toLowerCase().contains(needle))
          return false;
      }
      if (tier != null && tier.isNotEmpty && u.tier != tier) return false;
      if (testerLabel != null &&
          testerLabel.isNotEmpty &&
          u.testerLabel != testerLabel)
        return false;
      if (suspended != null && u.disabled != suspended) return false;
      if (status == 'active' && u.disabled) return false;
      if (status == 'suspended' && !u.disabled) return false;
      if (planExpiringBefore != null &&
          (u.planExpiresAt == null ||
              !u.planExpiresAt!.isBefore(planExpiringBefore)))
        return false;
      return true;
    }).toList();
    final start = int.tryParse(cursor ?? '') ?? 0;
    final size = limit < _pageSize ? limit : _pageSize;
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
        monthSpendUsd: 1.5,
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
    double? deltaUsd,
    double? budgetUsd,
    required String reason,
  }) async {
    _record(
      'credits:$id:delta=${deltaUsd ?? ''}:budget=${budgetUsd ?? ''}:$reason',
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
  );
}
