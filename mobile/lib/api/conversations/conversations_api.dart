import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../chat/chat_models.dart';
import '../errors.dart';

export '../chat/chat_models.dart';
export '../errors.dart';

/// HTTP client for Karmi conversation management and search.
class ConversationsApi {
  ConversationsApi({
    required this.baseUrl,
    http.Client? client,
    this.tokenProvider,
    this.timeout = const Duration(seconds: 20),
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final Duration timeout;
  final http.Client _client;

  /// Called for every request to provide the latest session bearer token.
  Future<String?> Function()? tokenProvider;

  /// Closes the underlying HTTP client.
  void close() => _client.close();

  /// Lists conversations for the current principal.
  ///
  /// Ordered by pinned DESC, updatedAt DESC, id DESC.
  /// When [archived] is false, returns active conversations (archivedAt == null).
  /// When [archived] is true, returns archived conversations (archivedAt != null).
  Future<ConversationPage> list({
    bool archived = false,
    String? cursor,
    int limit = 20,
  }) async {
    final query = <String, String>{
      'archived': archived.toString(),
      'limit': limit.toString(),
      if (cursor != null) 'cursor': cursor,
    };
    final body = await _send(
      'GET',
      '/v1/conversations',
      queryParameters: query,
    );
    return ConversationPage.fromJson(body as Map<String, dynamic>);
  }

  /// Searches non-deleted conversations by title and message content.
  Future<List<ConversationSearchResult>> search(
    String q, {
    int limit = 20,
  }) async {
    final query = <String, String>{'q': q, 'limit': limit.toString()};
    final body = await _send(
      'GET',
      '/v1/conversations/search',
      queryParameters: query,
    );
    return (body as List<dynamic>)
        .map(
          (e) => ConversationSearchResult.fromJson(e as Map<String, dynamic>),
        )
        .toList();
  }

  /// Fetches a single conversation by [id].
  Future<ConversationView> get(String id) async {
    final body = await _send(
      'GET',
      '/v1/conversations/${Uri.encodeComponent(id)}',
    );
    return ConversationView.fromJson(body as Map<String, dynamic>);
  }

  /// Fetches a page of messages for a conversation, ordered oldest to newest.
  ///
  /// When [before] is provided, returns messages older than that message id.
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    final query = <String, String>{
      'limit': limit.toString(),
      if (before != null) 'before': before,
    };
    final body = await _send(
      'GET',
      '/v1/conversations/${Uri.encodeComponent(id)}/messages',
      queryParameters: query,
    );
    return MessagePage.fromJson(body as Map<String, dynamic>);
  }

  /// Updates conversation properties (title, pinned, archived).
  ///
  /// Only provided (non-null) fields are sent in the request body.
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async {
    final json = <String, Object?>{
      if (title != null) 'title': title,
      if (pinned != null) 'pinned': pinned,
      if (archived != null) 'archived': archived,
    };
    final body = await _send(
      'PATCH',
      '/v1/conversations/${Uri.encodeComponent(id)}',
      json: json,
    );
    return ConversationView.fromJson(body as Map<String, dynamic>);
  }

  /// Soft deletes a conversation.
  Future<void> delete(String id) async {
    await _send('DELETE', '/v1/conversations/${Uri.encodeComponent(id)}');
  }

  /// Restores a soft-deleted conversation.
  Future<ConversationView> restore(String id) async {
    final body = await _send(
      'POST',
      '/v1/conversations/${Uri.encodeComponent(id)}/restore',
    );
    return ConversationView.fromJson(body as Map<String, dynamic>);
  }

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

  Future<Object?> _send(
    String method,
    String path, {
    Map<String, String>? queryParameters,
    Map<String, Object?>? json,
  }) async {
    final uri = _buildUri(path, queryParameters);
    final request = http.Request(method, uri);
    request.headers['Accept'] = 'application/json';
    if (tokenProvider != null) {
      final bearer = await tokenProvider!();
      if (bearer != null) {
        request.headers['Authorization'] = 'Bearer $bearer';
      }
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
    if (status == 401) {
      throw const UnauthorizedException();
    }
    throw ServerException(status);
  }
}
