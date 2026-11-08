import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../karmi_api.dart';
import 'bug_report_errors.dart';
import 'bug_report_models.dart';

/// HTTP client for Karmi Customer Bug Reports (`/v1/bug-reports`).
class BugReportsApi {
  BugReportsApi({
    required this.baseUrl,
    http.Client? client,
    this.tokenProvider,
    this.token,
    this.timeout = const Duration(seconds: 30),
  }) : _client = client ?? http.Client();

  /// Convenience constructor delegating configuration to [KarmiApi].
  factory BugReportsApi.fromApi(
    KarmiApi api, {
    http.Client? client,
    Duration? timeout,
  }) {
    return BugReportsApi(
      baseUrl: api.baseUrl,
      client: client,
      tokenProvider: api.tokenProvider,
      token: api.token,
      timeout: timeout ?? const Duration(seconds: 30),
    );
  }

  final String baseUrl;
  final Duration timeout;
  final http.Client _client;

  /// Dynamic bearer token provider (e.g. Clerk or session refresher).
  Future<String?> Function()? tokenProvider;

  /// Static bearer token fallback.
  String? token;

  /// Closes the underlying HTTP client.
  void close() => _client.close();

  Uri _buildUri(String path, [Map<String, String>? queryParameters]) {
    final normalizedBase = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final uri = Uri.parse('$normalizedBase$path');
    if (queryParameters == null || queryParameters.isEmpty) {
      return uri;
    }
    return uri.replace(queryParameters: queryParameters);
  }

  Future<String?> _resolveToken() async {
    if (tokenProvider != null) {
      final t = await tokenProvider!();
      if (t != null) return t;
    }
    return token;
  }

  /// Submits a bug report to `POST /v1/bug-reports`.
  ///
  /// Returns [BugReportCreated] on 201 (new) or 200 (idempotent replay).
  /// Throws typed [BugReportApiException] or [KarmiApiException] on failures.
  Future<BugReportCreated> submitBugReport(
    BugReportCreateRequest request,
  ) async {
    final uri = _buildUri('/v1/bug-reports');
    final httpRequest = http.Request('POST', uri);
    httpRequest.headers['Accept'] = 'application/json';
    httpRequest.headers['Content-Type'] = 'application/json';

    final bearer = await _resolveToken();
    if (bearer != null) {
      httpRequest.headers['Authorization'] = 'Bearer $bearer';
    }

    httpRequest.body = jsonEncode(request.toJson());

    final http.Response response;
    try {
      response = await http.Response.fromStream(
        await _client.send(httpRequest).timeout(timeout),
      ).timeout(timeout);
    } on SocketException {
      throw const NetworkException();
    } on http.ClientException {
      throw const NetworkException();
    } on TimeoutException {
      throw const ApiTimeoutException();
    }

    final status = response.statusCode;
    if (status == 200 || status == 201) {
      try {
        final decoded =
            jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
        return BugReportCreated.fromJson(decoded);
      } on FormatException {
        throw ServerException(status);
      }
    }

    final detail = _extractDetail(response.body);

    switch (status) {
      case 401:
        throw const UnauthorizedException();
      case 409:
        throw BugReportConflictException(
          detail is String
              ? detail
              : 'idempotency key was reused with a different payload',
        );
      case 413:
        throw BugReportPayloadTooLargeException(
          detail is String ? detail : 'screenshot exceeds 5 MB limit',
        );
      case 415:
        throw BugReportUnsupportedMediaTypeException(
          detail is String ? detail : 'unsupported screenshot content type',
        );
      case 422:
        throw BugReportValidationException(
          detail is String ? detail : 'validation failed',
        );
      case 429:
        final retryAfterHeader = response.headers['retry-after'];
        final seconds = int.tryParse(retryAfterHeader ?? '') ?? 86400;
        throw BugReportRateLimitException(retryAfterSeconds: seconds);
      default:
        throw ServerException(status);
    }
  }

  /// Alias for [submitBugReport].
  Future<BugReportCreated> submitReport(BugReportCreateRequest request) =>
      submitBugReport(request);

  /// Alias for [getBugReport].
  Future<BugReportDetail> getReport(String id) => getBugReport(id);

  /// Fetches an existing bug report by ID from `GET /v1/bug-reports/{id}`.
  Future<BugReportDetail> getBugReport(String id) async {
    final uri = _buildUri('/v1/bug-reports/${Uri.encodeComponent(id)}');
    final httpRequest = http.Request('GET', uri);
    httpRequest.headers['Accept'] = 'application/json';

    final bearer = await _resolveToken();
    if (bearer != null) {
      httpRequest.headers['Authorization'] = 'Bearer $bearer';
    }

    final http.Response response;
    try {
      response = await http.Response.fromStream(
        await _client.send(httpRequest).timeout(timeout),
      ).timeout(timeout);
    } on SocketException {
      throw const NetworkException();
    } on http.ClientException {
      throw const NetworkException();
    } on TimeoutException {
      throw const ApiTimeoutException();
    }

    final status = response.statusCode;
    if (status >= 200 && status < 300) {
      try {
        final decoded =
            jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
        return BugReportDetail.fromJson(decoded);
      } on FormatException {
        throw ServerException(status);
      }
    }

    if (status == 401) {
      throw const UnauthorizedException();
    }
    if (status == 404) {
      throw const BugReportNotFoundException();
    }
    throw ServerException(status);
  }

  static Object? _extractDetail(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map ? decoded['detail'] : null;
    } on FormatException {
      return null;
    }
  }
}
