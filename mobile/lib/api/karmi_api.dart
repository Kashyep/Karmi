import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'errors.dart';
import 'models.dart';

export 'errors.dart';
export 'models.dart';

/// HTTP client for the Daily Agent backend (`src/daily_agent/api.py`).
class KarmiApi {
  KarmiApi({
    this.baseUrl = defaultBaseUrl,
    http.Client? client,
    this.timeout = const Duration(seconds: 30),
    this.token,
  }) : _client = client ?? http.Client();

  /// `--dart-define=API_BASE_URL=...`; defaults to the Android emulator's host loopback.
  static const defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  final String baseUrl;
  final Duration timeout;
  final http.Client _client;

  /// Bearer token for `/v1/*`. Managed by `KarmiSession`.
  String? token;

  /// Called before an [UnauthorizedException] is thrown, so the session can end.
  void Function()? onUnauthorized;

  /// 32 hex chars from a CSPRNG (backend accepts 8–120 chars).
  static String newIdempotencyKey() {
    final rand = Random.secure();
    return List.generate(
      16,
      (_) => rand.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
  }

  /// `POST /dev/token` (development builds only; 404 elsewhere).
  Future<String> issueDevToken() async {
    final body = await _send('POST', '/dev/token', auth: false);
    return (body as Map<String, dynamic>)['token'] as String;
  }

  /// `POST /v1/messages`. Callers retrying the same message must pass the same
  /// [idempotencyKey] so the server replays instead of charging twice.
  Future<MessageView> sendMessage(
    String text, {
    required String idempotencyKey,
  }) async {
    final body = await _send(
      'POST',
      '/v1/messages',
      json: {'text': text, 'idempotency_key': idempotencyKey},
    );
    return MessageView.fromJson(body as Map<String, dynamic>);
  }

  Future<UsageView> getUsage() async => UsageView.fromJson(
    await _send('GET', '/v1/usage') as Map<String, dynamic>,
  );

  Future<List<NoteView>> listNotes() async {
    final body = await _send('GET', '/v1/notes') as List<dynamic>;
    return [for (final n in body) NoteView.fromJson(n as Map<String, dynamic>)];
  }

  Future<NoteView> createNote(
    String content, {
    required String idempotencyKey,
  }) async {
    final body = await _send(
      'POST',
      '/v1/notes',
      json: {'content': content, 'idempotency_key': idempotencyKey},
    );
    return NoteView.fromJson(body as Map<String, dynamic>);
  }

  Future<void> deleteNote(String id) =>
      _send('DELETE', '/v1/notes/${Uri.encodeComponent(id)}');

  Future<List<TaskView>> listTasks() async {
    final body = await _send('GET', '/v1/tasks') as List<dynamic>;
    return [for (final t in body) TaskView.fromJson(t as Map<String, dynamic>)];
  }

  Future<TaskView> completeTask(String id) async {
    final body = await _send(
      'PATCH',
      '/v1/tasks/${Uri.encodeComponent(id)}/complete',
    );
    return TaskView.fromJson(body as Map<String, dynamic>);
  }

  void close() => _client.close();

  Future<Object?> _send(
    String method,
    String path, {
    Map<String, Object?>? json,
    bool auth = true,
  }) async {
    final request = http.Request(method, Uri.parse('$baseUrl$path'));
    request.headers['Accept'] = 'application/json';
    if (auth && token != null) {
      request.headers['Authorization'] = 'Bearer $token';
    }
    if (json != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(json);
    }

    final http.Response response;
    try {
      response = await http.Response.fromStream(
        await _client.send(request).timeout(timeout),
      ).timeout(timeout);
    } on SocketException {
      throw const NetworkException();
    } on http.ClientException {
      throw const NetworkException();
    } on TimeoutException {
      throw const NetworkException();
    }

    final status = response.statusCode;
    if (status >= 200 && status < 300) {
      if (response.body.isEmpty) return null;
      try {
        return jsonDecode(utf8.decode(response.bodyBytes));
      } on FormatException {
        throw ServerException(status);
      }
    }
    throw _errorFor(status, response.body);
  }

  KarmiApiException _errorFor(int status, String body) {
    final detail = _detail(body);
    switch (status) {
      case 401:
        onUnauthorized?.call();
        return const UnauthorizedException();
      case 409:
        return detail is String && detail.contains('in flight')
            ? const InFlightException()
            : const IdempotencyConflictException();
      case 429:
        if (detail is Map && detail['code'] == 'ALLOWANCE_EXHAUSTED') {
          return LimitReachedException(
            resetAt: DateTime.tryParse('${detail['reset_at']}'),
          );
        }
        return const ServerException(429);
      default:
        return ServerException(status);
    }
  }

  static Object? _detail(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map ? decoded['detail'] : null;
    } on FormatException {
      return null;
    }
  }
}
