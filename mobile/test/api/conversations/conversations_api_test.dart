import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';

class _TrackingClient extends http.BaseClient {
  bool closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    return http.StreamedResponse(const Stream.empty(), 200);
  }

  @override
  void close() {
    closed = true;
  }
}

void main() {
  const baseUrl = 'http://api.test';

  group('ConversationsApi URL and query building', () {
    test(
      'list builds correct URL and query parameters with defaults',
      () async {
        late http.Request sentRequest;
        final client = MockClient((request) async {
          sentRequest = request;
          return http.Response(
            jsonEncode({'items': [], 'nextCursor': null}),
            200,
            headers: {'content-type': 'application/json'},
          );
        });
        final api = ConversationsApi(baseUrl: baseUrl, client: client);

        await api.list();

        expect(sentRequest.method, 'GET');
        expect(sentRequest.url.path, '/v1/conversations');
        expect(sentRequest.url.queryParameters, {
          'archived': 'false',
          'limit': '20',
        });
        expect(sentRequest.headers['Accept'], 'application/json');
      },
    );

    test('list includes cursor and custom limit when provided', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response(
          jsonEncode({'items': [], 'nextCursor': null}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      await api.list(archived: true, cursor: 'cur_base64_val', limit: 10);

      expect(sentRequest.method, 'GET');
      expect(sentRequest.url.path, '/v1/conversations');
      expect(sentRequest.url.queryParameters, {
        'archived': 'true',
        'cursor': 'cur_base64_val',
        'limit': '10',
      });
    });

    test('search builds correct path and query parameters', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response(
          jsonEncode([]),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      await api.search('meeting notes', limit: 30);

      expect(sentRequest.method, 'GET');
      expect(sentRequest.url.path, '/v1/conversations/search');
      expect(sentRequest.url.queryParameters, {
        'q': 'meeting notes',
        'limit': '30',
      });
    });

    test('get encodes conversation id into path', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response(
          jsonEncode({
            'id': 'conv 123/special',
            'title': 'Test',
            'updatedAt': '2026-10-21T10:00:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      await api.get('conv 123/special');

      expect(sentRequest.method, 'GET');
      expect(sentRequest.url.path, '/v1/conversations/conv%20123%2Fspecial');
    });

    test('messages builds correct path and query parameters', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response(
          jsonEncode({'items': [], 'hasMoreBefore': false}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      await api.messages('conv_1', before: 'msg_42', limit: 25);

      expect(sentRequest.method, 'GET');
      expect(sentRequest.url.path, '/v1/conversations/conv_1/messages');
      expect(sentRequest.url.queryParameters, {
        'limit': '25',
        'before': 'msg_42',
      });
    });

    test('restore builds correct path and method', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response(
          jsonEncode({
            'id': 'conv_1',
            'title': 'Restored Conv',
            'updatedAt': '2026-10-21T10:00:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      await api.restore('conv_1');

      expect(sentRequest.method, 'POST');
      expect(sentRequest.url.path, '/v1/conversations/conv_1/restore');
    });

    test('normalizes baseUrl with trailing slash', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response(
          jsonEncode({'items': [], 'nextCursor': null}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: 'http://api.test/', client: client);

      await api.list();

      expect(
        sentRequest.url.toString(),
        'http://api.test/v1/conversations?archived=false&limit=20',
      );
    });
  });

  group('Authorization header', () {
    test(
      'sends Bearer token when tokenProvider returns non-null token',
      () async {
        late http.Request sentRequest;
        final client = MockClient((request) async {
          sentRequest = request;
          return http.Response(
            jsonEncode({'items': []}),
            200,
            headers: {'content-type': 'application/json'},
          );
        });
        final api = ConversationsApi(
          baseUrl: baseUrl,
          client: client,
          tokenProvider: () async => 'clerk-jwt-token-xyz',
        );

        await api.list();

        expect(
          sentRequest.headers['Authorization'],
          'Bearer clerk-jwt-token-xyz',
        );
      },
    );

    test(
      'does not send Authorization header when tokenProvider returns null',
      () async {
        late http.Request sentRequest;
        final client = MockClient((request) async {
          sentRequest = request;
          return http.Response(
            jsonEncode({'items': []}),
            200,
            headers: {'content-type': 'application/json'},
          );
        });
        final api = ConversationsApi(
          baseUrl: baseUrl,
          client: client,
          tokenProvider: () async => null,
        );

        await api.list();

        expect(sentRequest.headers.containsKey('Authorization'), isFalse);
      },
    );

    test(
      'does not send Authorization header when tokenProvider is null',
      () async {
        late http.Request sentRequest;
        final client = MockClient((request) async {
          sentRequest = request;
          return http.Response(
            jsonEncode({'items': []}),
            200,
            headers: {'content-type': 'application/json'},
          );
        });
        final api = ConversationsApi(baseUrl: baseUrl, client: client);

        await api.list();

        expect(sentRequest.headers.containsKey('Authorization'), isFalse);
      },
    );
  });

  group('Model decoding', () {
    test('decodes ConversationPage from list', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'conv_1',
                'title': 'Quarterly Plan',
                'titleSource': 'user',
                'pinned': true,
                'archivedAt': '2026-10-20T12:00:00Z',
                'updatedAt': '2026-10-21T09:00:00Z',
                'lastMessageAt': '2026-10-21T09:30:00Z',
                'messageCount': 8,
              },
            ],
            'nextCursor': 'cursor_abc123',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      final page = await api.list();

      expect(page.items.length, 1);
      final item = page.items.first;
      expect(item.id, 'conv_1');
      expect(item.title, 'Quarterly Plan');
      expect(item.titleSource, 'user');
      expect(item.pinned, isTrue);
      expect(item.archivedAt, DateTime.parse('2026-10-20T12:00:00Z'));
      expect(item.updatedAt, DateTime.parse('2026-10-21T09:00:00Z'));
      expect(item.lastMessageAt, DateTime.parse('2026-10-21T09:30:00Z'));
      expect(item.messageCount, 8);
      expect(page.nextCursor, 'cursor_abc123');
    });

    test('decodes List<ConversationSearchResult> from search', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode([
            {
              'conversation': {
                'id': 'conv_2',
                'title': 'AI Architecture',
                'titleSource': 'auto',
                'pinned': false,
                'updatedAt': '2026-10-21T08:00:00Z',
                'messageCount': 3,
              },
              'snippet': '...discussing AI Architecture patterns...',
              'matched': 'title',
            },
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      final results = await api.search('architecture');

      expect(results.length, 1);
      expect(results.first.conversation.id, 'conv_2');
      expect(results.first.conversation.title, 'AI Architecture');
      expect(
        results.first.snippet,
        '...discussing AI Architecture patterns...',
      );
      expect(results.first.matched, 'title');
    });

    test('decodes MessagePage from messages', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'msg_1',
                'conversationId': 'conv_1',
                'role': 'user',
                'status': 'complete',
                'content': 'How does routing work?',
                'createdAt': '2026-10-21T09:00:00Z',
                'updatedAt': '2026-10-21T09:00:00Z',
              },
              {
                'id': 'msg_2',
                'conversationId': 'conv_1',
                'role': 'assistant',
                'status': 'complete',
                'content': 'Routing directs incoming queries.',
                'finishReason': 'stop',
                'createdAt': '2026-10-21T09:00:02Z',
                'updatedAt': '2026-10-21T09:00:02Z',
              },
            ],
            'hasMoreBefore': true,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      final page = await api.messages('conv_1');

      expect(page.hasMoreBefore, isTrue);
      expect(page.items.length, 2);
      expect(page.items[0].id, 'msg_1');
      expect(page.items[0].conversationId, 'conv_1');
      expect(page.items[0].role, 'user');
      expect(page.items[0].status, MessageStatus.complete);
      expect(page.items[0].content, 'How does routing work?');
      expect(page.items[1].id, 'msg_2');
      expect(page.items[1].role, 'assistant');
      expect(page.items[1].finishReason, FinishReason.stop);
    });

    test('decodes ConversationView from get', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'id': 'conv_1',
            'title': 'Test Conv',
            'titleSource': 'auto',
            'pinned': false,
            'updatedAt': '2026-10-21T09:00:00Z',
            'messageCount': 1,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      final conv = await api.get('conv_1');

      expect(conv.id, 'conv_1');
      expect(conv.title, 'Test Conv');
      expect(conv.messageCount, 1);
    });

    test('decodes ConversationView from restore', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'id': 'conv_1',
            'title': 'Restored Conv',
            'titleSource': 'user',
            'pinned': false,
            'updatedAt': '2026-10-21T09:00:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      final conv = await api.restore('conv_1');

      expect(conv.id, 'conv_1');
      expect(conv.title, 'Restored Conv');
    });
  });

  group('PATCH body contents', () {
    test('sends only provided fields in JSON payload', () async {
      final capturedRequests = <http.Request>[];
      final client = MockClient((request) async {
        capturedRequests.add(request);
        return http.Response(
          jsonEncode({
            'id': 'conv_1',
            'title': 'Updated Title',
            'pinned': true,
            'updatedAt': '2026-10-21T10:00:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      // Only title
      await api.update('conv_1', title: 'Updated Title');
      expect(capturedRequests[0].method, 'PATCH');
      expect(capturedRequests[0].url.path, '/v1/conversations/conv_1');
      expect(capturedRequests[0].headers['Content-Type'], 'application/json');
      expect(jsonDecode(capturedRequests[0].body), {'title': 'Updated Title'});

      // Only pinned
      await api.update('conv_1', pinned: true);
      expect(jsonDecode(capturedRequests[1].body), {'pinned': true});

      // Only archived
      await api.update('conv_1', archived: true);
      expect(jsonDecode(capturedRequests[2].body), {'archived': true});

      // All fields
      await api.update(
        'conv_1',
        title: 'Renamed',
        pinned: false,
        archived: false,
      );
      expect(jsonDecode(capturedRequests[3].body), {
        'title': 'Renamed',
        'pinned': false,
        'archived': false,
      });
    });
  });

  group('DELETE conversation', () {
    test('returns void on 204 No Content', () async {
      late http.Request sentRequest;
      final client = MockClient((request) async {
        sentRequest = request;
        return http.Response('', 204);
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      await expectLater(api.delete('conv_123'), completes);
      expect(sentRequest.method, 'DELETE');
      expect(sentRequest.url.path, '/v1/conversations/conv_123');
    });
  });

  group('Error mappings', () {
    test('401 maps to UnauthorizedException', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'unauthorized'}),
          401,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      expect(() => api.list(), throwsA(isA<UnauthorizedException>()));
    });

    test('404 maps to ServerException with statusCode 404', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'conversation not found'}),
          404,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      try {
        await api.get('conv_missing');
        fail('Expected ServerException');
      } on ServerException catch (e) {
        expect(e.statusCode, 404);
      }
    });

    test(
      'other non-2xx status maps to ServerException with statusCode',
      () async {
        final client = MockClient((request) async {
          return http.Response('server error', 500);
        });
        final api = ConversationsApi(baseUrl: baseUrl, client: client);

        try {
          await api.delete('conv_1');
          fail('Expected ServerException');
        } on ServerException catch (e) {
          expect(e.statusCode, 500);
        }
      },
    );

    test('invalid JSON on 200 maps to ServerException', () async {
      final client = MockClient((request) async {
        return http.Response('not valid json {', 200);
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      try {
        await api.get('conv_1');
        fail('Expected ServerException');
      } on ServerException catch (e) {
        expect(e.statusCode, 200);
      }
    });

    test('SocketException maps to NetworkException', () async {
      final client = MockClient((request) async {
        throw const SocketException('offline');
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      expect(() => api.list(), throwsA(isA<NetworkException>()));
    });

    test('ClientException maps to NetworkException', () async {
      final client = MockClient((request) async {
        throw http.ClientException('connection failed');
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      expect(() => api.list(), throwsA(isA<NetworkException>()));
    });

    test('TimeoutException maps to NetworkException', () async {
      final client = MockClient((request) async {
        throw TimeoutException('request timed out');
      });
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      expect(() => api.list(), throwsA(isA<NetworkException>()));
    });
  });

  group('Lifecycle', () {
    test('close closes the underlying client', () {
      final client = _TrackingClient();
      final api = ConversationsApi(baseUrl: baseUrl, client: client);

      api.close();

      expect(client.closed, isTrue);
    });
  });
}
