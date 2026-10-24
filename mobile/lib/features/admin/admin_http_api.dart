import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'admin_api.dart';

/// [AdminApi] over HTTP (`/v1/admin/*`). Shares the app's http client and
/// bearer token provider; the admin session token travels as
/// `X-Admin-Session` and is never persisted here.
class HttpAdminApi implements AdminApi {
  HttpAdminApi({
    required this.baseUrl,
    required http.Client client,
    required this.tokenProvider,
    this.timeout = const Duration(seconds: 20),
  }) : _client = client;

  final String baseUrl;
  final http.Client _client;
  final Future<String?> Function() tokenProvider;
  final Duration timeout;

  static const _session = '/v1/admin/session';
  static const _users = '/v1/admin/users';

  @override
  Future<void> probe() async {
    // 2xx (including 200 {valid:false}) and 401 ADMIN_SESSION_REQUIRED mean
    // the account is eligible; 403 ADMIN_FORBIDDEN and everything else do not.
    await _send('GET', _session, allowNoAdminSession: true);
  }

  @override
  Future<AdminSessionGrant> openSession(String code) async {
    final resp = await _send('POST', _session, body: {'code': code});
    final j = _object(resp);
    final expiresAt = DateTime.tryParse(j['expires_at'] as String? ?? '');
    final token = j['admin_session_token'] as String?;
    if (token == null || token.isEmpty || expiresAt == null) {
      throw AdminFailure(resp.statusCode);
    }
    return AdminSessionGrant(token: token, expiresAt: expiresAt);
  }

  @override
  Future<void> closeSession(String token) async {
    await _send('DELETE', _session, adminToken: token);
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
    final resp = await _send(
      'GET',
      _users,
      adminToken: token,
      query: {
        'limit': '$limit',
        if (q != null && q.isNotEmpty) 'q': q,
        if (tier != null && tier.isNotEmpty) 'tier': tier,
        if (status != null && status.isNotEmpty) 'status': status,
        if (testerLabel != null && testerLabel.isNotEmpty)
          'tester_label': testerLabel,
        if (suspended != null) 'suspended': '$suspended',
        if (planExpiringBefore != null)
          'plan_expiring_before': planExpiringBefore.toUtc().toIso8601String(),
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
      },
    );
    return _parse(resp, AdminUserPage.fromJson);
  }

  @override
  Future<AdminUserDetail> getUser(String token, String id) async {
    final resp = await _send('GET', '$_users/${_id(id)}', adminToken: token);
    return _parse(resp, AdminUserDetail.fromJson);
  }

  @override
  Future<void> suspend(String token, String id, {required String reason}) =>
      _mutate(token, id, 'suspend', {'reason': reason});

  @override
  Future<void> unsuspend(String token, String id, {required String reason}) =>
      _mutate(token, id, 'unsuspend', {'reason': reason});

  @override
  Future<void> revokeSessions(
    String token,
    String id, {
    required String reason,
  }) => _mutate(token, id, 'revoke-sessions', {'reason': reason});

  @override
  Future<void> editUser(
    String token,
    String id, {
    String? displayName,
    bool? tester,
    String? testerLabel,
    String? adminNotes,
    required String reason,
  }) => _send(
    'PATCH',
    '$_users/${_id(id)}',
    adminToken: token,
    body: {
      if (displayName != null) 'display_name': displayName,
      if (tester != null) 'tester': tester,
      if (testerLabel != null) 'tester_label': testerLabel,
      if (adminNotes != null) 'admin_notes': adminNotes,
      'reason': reason,
    },
  ).then((_) {});

  @override
  Future<void> changeTier(
    String token,
    String id, {
    required String tier,
    required String reason,
    DateTime? expiresAt,
  }) => _mutate(token, id, 'tier', {
    'tier': tier,
    if (expiresAt != null) 'expires_at': expiresAt.toUtc().toIso8601String(),
    'reason': reason,
  });

  @override
  Future<void> bulkTier(
    String token,
    List<String> userIds, {
    required String tier,
    required String reason,
    DateTime? expiresAt,
  }) async {
    assert(userIds.isNotEmpty && userIds.length <= 100);
    await _send(
      'POST',
      '$_users/bulk-tier',
      adminToken: token,
      body: {
        'user_ids': userIds,
        'tier': tier,
        if (expiresAt != null)
          'expires_at': expiresAt.toUtc().toIso8601String(),
        'reason': reason,
      },
    );
  }

  @override
  Future<void> adjustCredits(
    String token,
    String id, {
    double? deltaUsd,
    double? budgetUsd,
    required String reason,
  }) {
    assert((deltaUsd == null) != (budgetUsd == null));
    return _mutate(token, id, 'credits', {
      if (deltaUsd != null) 'delta_usd': deltaUsd,
      if (budgetUsd != null) 'budget_usd': budgetUsd,
      'reason': reason,
    });
  }

  @override
  Future<String> exportUser(
    String token,
    String id, {
    required String reason,
  }) async {
    assert(reason.trim().isNotEmpty);
    final resp = await _send(
      'GET',
      '$_users/${_id(id)}/export',
      adminToken: token,
      query: {'reason': reason},
    );
    final decoded = _json(resp);
    return const JsonEncoder.withIndent('  ').convert(decoded);
  }

  @override
  Future<void> deleteUser(
    String token,
    String id, {
    required String reason,
  }) async {
    assert(reason.trim().isNotEmpty);
    await _send(
      'DELETE',
      '$_users/${_id(id)}',
      adminToken: token,
      body: {'reason': reason, 'confirm': 'DELETE'},
    );
  }

  @override
  Future<AdminMonitor> monitor(String token) async {
    final resp = await _send('GET', '/v1/admin/monitor', adminToken: token);
    return _parse(resp, AdminMonitor.fromJson);
  }

  @override
  Future<AuditPage> audit(
    String token, {
    int limit = 50,
    String? cursor,
  }) async {
    final resp = await _send(
      'GET',
      '/v1/admin/audit',
      adminToken: token,
      query: {
        'limit': '$limit',
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
      },
    );
    return _parse(resp, AuditPage.fromJson);
  }

  Future<void> _mutate(
    String token,
    String id,
    String action,
    Map<String, Object?> body,
  ) async {
    assert((body['reason'] as String?)?.trim().isNotEmpty ?? false);
    await _send(
      'POST',
      '$_users/${_id(id)}/$action',
      adminToken: token,
      body: body,
    );
  }

  static String _id(String id) => Uri.encodeComponent(id);

  Uri _uri(String path, Map<String, String>? query) {
    final base = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse(
      '$base$path',
    ).replace(queryParameters: (query == null || query.isEmpty) ? null : query);
  }

  /// Sends one request and maps every non-2xx status to an [AdminException].
  /// Returns the response for 2xx (and for the probe's "no admin session"
  /// 401 when [allowNoAdminSession] is set).
  Future<http.Response> _send(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
    String? adminToken,
    bool allowNoAdminSession = false,
  }) async {
    final headers = <String, String>{'Accept': 'application/json'};
    final bearer = await tokenProvider();
    if (bearer != null && bearer.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearer';
    }
    if (adminToken != null) headers['X-Admin-Session'] = adminToken;

    final request = http.Request(method, _uri(path, query))
      ..headers.addAll(headers);
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }

    final http.Response resp;
    try {
      final streamed = await _client.send(request).timeout(timeout);
      resp = await http.Response.fromStream(streamed).timeout(timeout);
    } on TimeoutException {
      throw const AdminFailure();
    } on IOException {
      throw const AdminFailure();
    } on http.ClientException {
      throw const AdminFailure();
    }

    final status = resp.statusCode;
    if (status >= 200 && status < 300) return resp;
    if (allowNoAdminSession &&
        status == 401 &&
        _errorCode(resp) == 'ADMIN_SESSION_REQUIRED') {
      return resp;
    }
    switch (status) {
      case 401:
        throw const AdminUnauthorized();
      case 403:
        // ADMIN_TARGET_PROTECTED refuses one action (acting on another admin);
        // the caller is still an admin, so it must not hide the console.
        if (_errorCode(resp) == 'ADMIN_TARGET_PROTECTED') {
          throw AdminFailure(status);
        }
        throw const AdminForbidden();
      case 423:
        throw AdminLockedOut(_retryAfter(resp));
      default:
        throw AdminFailure(status);
    }
  }

  /// `detail.code` of an error body, or null.
  static String? _errorCode(http.Response resp) {
    try {
      final decoded = jsonDecode(_bodyText(resp));
      if (decoded is Map && decoded['detail'] is Map) {
        final code = (decoded['detail'] as Map)['code'];
        if (code is String) return code;
      }
    } on FormatException {
      // Not JSON: no code.
    }
    return null;
  }

  static String _bodyText(http.Response resp) {
    try {
      return utf8.decode(resp.bodyBytes, allowMalformed: true);
    } on FormatException {
      return '';
    }
  }

  /// `retry_after` (seconds) at the top level or nested under `detail`, then
  /// the standard `Retry-After` header. Missing values mean zero.
  static Duration _retryAfter(http.Response resp) {
    num? seconds;
    try {
      final decoded = jsonDecode(_bodyText(resp));
      if (decoded is Map) {
        final detail = decoded['detail'];
        final raw =
            decoded['retry_after'] ??
            (detail is Map ? detail['retry_after'] : null);
        if (raw is num) seconds = raw;
      }
    } on FormatException {
      // Fall through to the header.
    }
    seconds ??= num.tryParse(resp.headers['retry-after'] ?? '');
    if (seconds == null || seconds.isNegative) return Duration.zero;
    return Duration(seconds: seconds.ceil());
  }

  /// Decodes a JSON body; malformed bodies become [AdminFailure].
  static Object? _json(http.Response resp) {
    try {
      return jsonDecode(utf8.decode(resp.bodyBytes));
    } on FormatException {
      throw AdminFailure(resp.statusCode);
    }
  }

  static Map<String, dynamic> _object(http.Response resp) {
    final decoded = _json(resp);
    if (decoded is Map<String, dynamic>) return decoded;
    throw AdminFailure(resp.statusCode);
  }

  /// Parses a JSON object with [fromJson]; shape errors become [AdminFailure].
  static T _parse<T>(
    http.Response resp,
    T Function(Map<String, dynamic>) fromJson,
  ) {
    final j = _object(resp);
    try {
      return fromJson(j);
    } on TypeError {
      throw AdminFailure(resp.statusCode);
    } on FormatException {
      throw AdminFailure(resp.statusCode);
    }
  }
}
