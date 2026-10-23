import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../karmi_api.dart';
import 'run_events.dart';
import 'sse_parser.dart';

export 'run_events.dart';
export 'sse_parser.dart';

/// HTTP and Server-Sent Events client for Karmi chat runs and streaming.
class RunStreamClient {
  RunStreamClient({
    String? baseUrl,
    http.Client? client,
    Duration? timeout,
    this.token,
    this.tokenProvider,
    this.onUnauthorized,
    this.api,
  }) : baseUrl = baseUrl ?? api?.baseUrl ?? KarmiApi.defaultBaseUrl,
       timeout = timeout ?? api?.timeout ?? const Duration(seconds: 60),
       _client = client ?? http.Client();

  /// Creates a [RunStreamClient] inheriting base URL, token, and callbacks from [api].
  factory RunStreamClient.fromApi(
    KarmiApi api, {
    http.Client? client,
    Duration? timeout,
  }) {
    return RunStreamClient(
      baseUrl: api.baseUrl,
      client: client ?? api.client,
      timeout: timeout ?? api.timeout,
      token: api.token,
      tokenProvider: api.tokenProvider,
      onUnauthorized: api.onUnauthorized,
      api: api,
    );
  }

  /// Backend base URL (defaults to `KarmiApi.defaultBaseUrl`).
  final String baseUrl;

  /// Timeout for connecting and completing HTTP requests.
  final Duration timeout;

  /// Optional underlying [KarmiApi] used as fallback for configuration.
  final KarmiApi? api;

  /// Bearer token for authenticated requests.
  String? token;

  /// Provider for dynamic or refreshed tokens.
  Future<String?> Function()? tokenProvider;

  /// Callback invoked when HTTP 401 Unauthorized is received.
  void Function()? onUnauthorized;

  final http.Client _client;

  int _lastSeq = 0;

  /// The most recent sequence number observed across all runs.
  int get lastSeq => _lastSeq;

  /// Starts a new chat run via `POST /v1/chat/stream`.
  Stream<RunEvent> startRun({
    required String text,
    String? conversationId,
    required String clientMessageId,
  }) async* {
    final url = Uri.parse('$baseUrl/v1/chat/stream');
    final request = http.Request('POST', url);
    final headers = await _buildHeaders(auth: true, sse: true, json: true);
    request.headers.addAll(headers);
    request.body = jsonEncode({
      'text': text,
      'client_message_id': clientMessageId,
      if (conversationId != null) 'conversation_id': conversationId,
    });

    yield* _streamRequest(request);
  }

  /// Resumes an existing run from [afterSeq] via `GET /v1/runs/{id}/events?after_seq=N`.
  Stream<RunEvent> resumeRun({
    required String runId,
    required int afterSeq,
  }) async* {
    final url = Uri.parse(
      '$baseUrl/v1/runs/${Uri.encodeComponent(runId)}/events?after_seq=$afterSeq',
    );
    final request = http.Request('GET', url);
    final headers = await _buildHeaders(auth: true, sse: true, json: false);
    request.headers.addAll(headers);

    yield* _streamRequest(request, initialSeq: afterSeq);
  }

  /// Appends continuation content to an assistant message via `POST /v1/messages/{id}/continue`.
  Stream<RunEvent> continueMessage(String assistantMessageId) async* {
    final url = Uri.parse(
      '$baseUrl/v1/messages/${Uri.encodeComponent(assistantMessageId)}/continue',
    );
    final request = http.Request('POST', url);
    final headers = await _buildHeaders(auth: true, sse: true, json: true);
    request.headers.addAll(headers);
    request.body = '{}';

    yield* _streamRequest(request);
  }

  /// Regenerates an assistant message via `POST /v1/messages/{id}/regenerate`.
  Stream<RunEvent> regenerateMessage(String assistantMessageId) async* {
    final url = Uri.parse(
      '$baseUrl/v1/messages/${Uri.encodeComponent(assistantMessageId)}/regenerate',
    );
    final request = http.Request('POST', url);
    final headers = await _buildHeaders(auth: true, sse: true, json: true);
    request.headers.addAll(headers);
    request.body = '{}';

    yield* _streamRequest(request);
  }

  /// Cancels an in-flight run via `POST /v1/runs/{id}/stop`.
  Future<void> stopRun(String runId) async {
    final url = Uri.parse(
      '$baseUrl/v1/runs/${Uri.encodeComponent(runId)}/stop',
    );
    final request = http.Request('POST', url);
    final headers = await _buildHeaders(auth: true, sse: false, json: true);
    request.headers.addAll(headers);
    request.body = '{}';

    final http.StreamedResponse response;
    try {
      response = await _client.send(request).timeout(timeout);
    } on SocketException catch (e) {
      throw RunStreamException(
        category: ErrorCategory.network,
        message: e.toString(),
      );
    } on http.ClientException catch (e) {
      throw RunStreamException(
        category: ErrorCategory.network,
        message: e.toString(),
      );
    } on TimeoutException catch (e) {
      throw RunStreamException(
        category: ErrorCategory.timeout,
        message: e.toString(),
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final body = await response.stream.bytesToString();
      throw _mapHttpError(response.statusCode, body);
    }
  }

  /// Resolves the bearer token from configured provider or token properties.
  Future<String?> _resolveToken() async {
    if (tokenProvider != null) {
      return await tokenProvider!();
    }
    if (api?.tokenProvider != null) {
      return await api!.tokenProvider!();
    }
    return token ?? api?.token;
  }

  /// Builds request headers including auth, accept, and content-type.
  Future<Map<String, String>> _buildHeaders({
    required bool auth,
    required bool sse,
    required bool json,
  }) async {
    final headers = <String, String>{};
    if (sse) {
      headers['Accept'] = 'text/event-stream';
      headers['Cache-Control'] = 'no-cache';
    } else {
      headers['Accept'] = 'application/json';
    }
    if (json) {
      headers['Content-Type'] = 'application/json';
    }
    if (auth) {
      final bearer = await _resolveToken();
      if (bearer != null) {
        headers['Authorization'] = 'Bearer $bearer';
      }
    }
    return headers;
  }

  /// Streams and parses an SSE response, updating sequence tracking and error states.
  Stream<RunEvent> _streamRequest(
    http.Request request, {
    int? initialSeq,
  }) async* {
    final http.StreamedResponse response;
    try {
      response = await _client.send(request).timeout(timeout);
    } on SocketException catch (e) {
      throw RunStreamException(
        category: ErrorCategory.network,
        message: e.toString(),
        lastSeq: initialSeq ?? _lastSeq,
      );
    } on http.ClientException catch (e) {
      throw RunStreamException(
        category: ErrorCategory.network,
        message: e.toString(),
        lastSeq: initialSeq ?? _lastSeq,
      );
    } on TimeoutException catch (e) {
      throw RunStreamException(
        category: ErrorCategory.timeout,
        message: e.toString(),
        lastSeq: initialSeq ?? _lastSeq,
      );
    } catch (e) {
      throw RunStreamException(
        category: ErrorCategory.network,
        message: e.toString(),
        lastSeq: initialSeq ?? _lastSeq,
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final body = await response.stream.bytesToString();
      throw _mapHttpError(response.statusCode, body);
    }

    int localLastSeq = initialSeq ?? _lastSeq;
    bool hasSeenTerminal = false;

    final sseStream = SseParser.parseBytes(response.stream);

    try {
      await for (final message in sseStream) {
        final eventName = message.event ?? 'message';
        Map<String, dynamic> data = const {};
        if (message.data.isNotEmpty) {
          try {
            final decoded = jsonDecode(message.data);
            if (decoded is Map<String, dynamic>) {
              data = decoded;
            }
          } catch (_) {
            data = const {};
          }
        }

        final RunEvent event;
        try {
          event = ChatStreamEvent.fromEvent(
            eventName,
            data,
            id: message.idAsInt,
          );
        } catch (_) {
          continue;
        }

        if (event is MessageDeltaEvent) {
          if (event.seq != null) {
            localLastSeq = event.seq!;
            _lastSeq = event.seq!;
          }
        } else if (event is RunStartedEvent) {
          localLastSeq = event.seq;
          _lastSeq = event.seq;
        } else if (message.idAsInt != null) {
          localLastSeq = message.idAsInt!;
          _lastSeq = message.idAsInt!;
        }

        if (event is RunFinishedEvent || event is RunErrorEvent) {
          hasSeenTerminal = true;
        }

        yield event;
      }
    } on RunStreamException {
      rethrow;
    } catch (e) {
      if (!hasSeenTerminal) {
        throw RunStreamException(
          category: ErrorCategory.network,
          message: e.toString(),
          lastSeq: localLastSeq,
        );
      }
      return;
    }

    if (!hasSeenTerminal) {
      throw RunStreamException(
        category: ErrorCategory.network,
        message: 'Connection closed before terminal event',
        lastSeq: localLastSeq,
      );
    }
  }

  /// Maps non-2xx HTTP responses and JSON error envelopes to [RunStreamException].
  RunStreamException _mapHttpError(int status, String body) {
    Object? detail;
    String? categoryStr;
    String? code;
    int? retryAfterSeconds;

    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        detail = decoded['detail'];
        categoryStr = decoded['category'] as String?;
        retryAfterSeconds =
            (decoded['retry_after_s'] ?? decoded['retryAfterSeconds']) as int?;
        if (detail is Map<String, dynamic>) {
          code = detail['code'] as String?;
          categoryStr ??= detail['category'] as String?;
          retryAfterSeconds ??=
              (detail['retry_after_s'] ?? detail['retryAfterSeconds']) as int?;
        } else if (detail is String) {
          code = detail;
        }
      }
    } catch (_) {}

    void triggerUnauthorized() {
      onUnauthorized?.call();
      api?.onUnauthorized?.call();
    }

    // 1. Explicit category wire name in payload
    if (categoryStr != null) {
      final cat = ErrorCategory.fromWire(categoryStr);
      if (cat != null) {
        if (cat == ErrorCategory.unauthorized) {
          triggerUnauthorized();
        }
        return RunStreamException(
          category: cat,
          message: body,
          retryAfterSeconds: retryAfterSeconds,
        );
      }
    }

    // 2. HTTP 401 Unauthorized
    if (status == 401) {
      triggerUnauthorized();
      return RunStreamException(
        category: ErrorCategory.unauthorized,
        message: body,
        retryAfterSeconds: retryAfterSeconds,
      );
    }

    // 3. HTTP 429 Quota or Capacity
    if (status == 429) {
      if (code == 'ALLOWANCE_EXHAUSTED' ||
          body.contains('ALLOWANCE_EXHAUSTED')) {
        return RunStreamException(
          category: ErrorCategory.quotaExhausted,
          message: body,
          retryAfterSeconds: retryAfterSeconds,
        );
      }
      if (code == 'BETA_CAPACITY_FULL' || body.contains('BETA_CAPACITY_FULL')) {
        return RunStreamException(
          category: ErrorCategory.capacityFull,
          message: body,
          retryAfterSeconds: retryAfterSeconds,
        );
      }
      return RunStreamException(
        category: ErrorCategory.quotaExhausted,
        message: body,
        retryAfterSeconds: retryAfterSeconds,
      );
    }

    // 4. HTTP 422 Validation Failed
    if (status == 422) {
      return RunStreamException(
        category: ErrorCategory.validationFailed,
        message: body,
        retryAfterSeconds: retryAfterSeconds,
      );
    }

    // 5. HTTP 404 Resume Unavailable / Not Found
    if (status == 404) {
      return RunStreamException(
        category: ErrorCategory.resumeUnavailable,
        message: body,
        retryAfterSeconds: retryAfterSeconds,
      );
    }

    // 6. HTTP 502/503/504 Provider Unavailable
    if (status == 502 || status == 503 || status == 504) {
      return RunStreamException(
        category: ErrorCategory.providerUnavailable,
        message: body,
        retryAfterSeconds: retryAfterSeconds,
      );
    }

    // 7. General 5xx
    if (status >= 500) {
      return RunStreamException(
        category: ErrorCategory.providerUnavailable,
        message: body,
        retryAfterSeconds: retryAfterSeconds,
      );
    }

    // 8. Default Internal
    return RunStreamException(
      category: ErrorCategory.internal,
      message: body,
      retryAfterSeconds: retryAfterSeconds,
    );
  }
}
