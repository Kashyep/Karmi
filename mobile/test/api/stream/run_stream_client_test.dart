import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';

void main() {
  group('RunStreamClient', () {
    test('startRun: happy path streams events and updates lastSeq', () async {
      late http.Request recordedRequest;

      final mockClient = MockClient.streaming((request, bodyStream) async {
        recordedRequest = request as http.Request;
        final responseText =
            'event: run.started\n'
            'data: {"run_id":"run_100","conversation_id":"conv_1","user_message_id":"msg_u","assistant_message_id":"msg_a","seq":0}\n\n'
            'id: 1\n'
            'event: message.delta\n'
            'data: {"text":"Namaste"}\n\n'
            'id: 2\n'
            'event: message.delta\n'
            'data: {"text":"!"}\n\n'
            'event: run.finished\n'
            'data: {"finish_reason":"stop","outcome":"success","input_tokens":10,"output_tokens":5}\n\n';

        final stream = Stream.value(utf8.encode(responseText));
        return http.StreamedResponse(
          stream,
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
        token: 'test-token',
      );

      final events = await client
          .startRun(
            text: 'Hello',
            clientMessageId: 'cmid_001',
            conversationId: 'conv_1',
          )
          .toList();

      expect(recordedRequest.method, 'POST');
      expect(recordedRequest.url.path, '/v1/chat/stream');
      expect(recordedRequest.headers['Authorization'], 'Bearer test-token');
      expect(recordedRequest.headers['Accept'], 'text/event-stream');

      final body = jsonDecode(recordedRequest.body) as Map<String, dynamic>;
      expect(body['text'], 'Hello');
      expect(body['client_message_id'], 'cmid_001');
      expect(body['conversation_id'], 'conv_1');

      expect(events.length, 4);

      final started = events[0] as RunStartedEvent;
      expect(started.runId, 'run_100');
      expect(started.conversationId, 'conv_1');

      final delta1 = events[1] as MessageDeltaEvent;
      expect(delta1.text, 'Namaste');
      expect(delta1.seq, 1);

      final delta2 = events[2] as MessageDeltaEvent;
      expect(delta2.text, '!');
      expect(delta2.seq, 2);

      final finished = events[3] as RunFinishedEvent;
      expect(finished.finishReason, FinishReason.stop);

      expect(client.lastSeq, 2);
    });

    test('resumeRun: requests events after_seq and streams replay', () async {
      late http.Request recordedRequest;

      final mockClient = MockClient.streaming((request, bodyStream) async {
        recordedRequest = request as http.Request;
        final responseText =
            'id: 6\n'
            'event: message.delta\n'
            'data: {"text":" resumed"}\n\n'
            'event: run.finished\n'
            'data: {"finish_reason":"stop"}\n\n';

        return http.StreamedResponse(
          Stream.value(utf8.encode(responseText)),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
      );

      final events = await client
          .resumeRun(runId: 'run_123', afterSeq: 5)
          .toList();

      expect(recordedRequest.method, 'GET');
      expect(
        recordedRequest.url.toString(),
        'http://test.karmi.ai/v1/runs/run_123/events?after_seq=5',
      );

      expect(events.length, 2);
      expect((events[0] as MessageDeltaEvent).seq, 6);
      expect((events[1] as RunFinishedEvent).finishReason, FinishReason.stop);
      expect(client.lastSeq, 6);
    });

    test('continueMessage: posts to messages/{id}/continue', () async {
      late http.Request recordedRequest;

      final mockClient = MockClient.streaming((request, bodyStream) async {
        recordedRequest = request as http.Request;
        final responseText =
            'event: run.started\n'
            'data: {"run_id":"r2","conversation_id":"c1","user_message_id":"u1","assistant_message_id":"msg_cont","seq":0}\n\n'
            'event: run.finished\n'
            'data: {"finish_reason":"stop"}\n\n';

        return http.StreamedResponse(
          Stream.value(utf8.encode(responseText)),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
      );

      final events = await client.continueMessage('msg_cont').toList();

      expect(recordedRequest.method, 'POST');
      expect(recordedRequest.url.path, '/v1/messages/msg_cont/continue');
      expect(events.length, 2);
    });

    test('regenerateMessage: posts to messages/{id}/regenerate', () async {
      late http.Request recordedRequest;

      final mockClient = MockClient.streaming((request, bodyStream) async {
        recordedRequest = request as http.Request;
        final responseText =
            'event: run.started\n'
            'data: {"run_id":"r3","conversation_id":"c1","user_message_id":"u1","assistant_message_id":"msg_regen","seq":0}\n\n'
            'event: run.finished\n'
            'data: {"finish_reason":"stop"}\n\n';

        return http.StreamedResponse(
          Stream.value(utf8.encode(responseText)),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
      );

      final events = await client.regenerateMessage('msg_regen').toList();

      expect(recordedRequest.method, 'POST');
      expect(recordedRequest.url.path, '/v1/messages/msg_regen/regenerate');
      expect(events.length, 2);
    });

    test('stopRun: posts to runs/{id}/stop and handles 202 status', () async {
      late http.Request recordedRequest;

      final mockClient = MockClient.streaming((request, bodyStream) async {
        recordedRequest = request as http.Request;
        return http.StreamedResponse(
          Stream.value(utf8.encode('{"status":"cancelled"}')),
          202,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
      );

      await expectLater(client.stopRun('run_target'), completes);
      expect(recordedRequest.method, 'POST');
      expect(recordedRequest.url.path, '/v1/runs/run_target/stop');
    });

    test(
      'pre-stream error: 429 ALLOWANCE_EXHAUSTED maps to quotaExhausted',
      () async {
        final mockClient = MockClient.streaming((request, bodyStream) async {
          final errorJson = jsonEncode({
            'detail': {
              'code': 'ALLOWANCE_EXHAUSTED',
              'reset_at': '2026-10-22T00:00:00Z',
            },
          });
          return http.StreamedResponse(
            Stream.value(utf8.encode(errorJson)),
            429,
            headers: {'content-type': 'application/json'},
          );
        });

        final client = RunStreamClient(
          baseUrl: 'http://test.karmi.ai',
          client: mockClient,
        );

        try {
          await client
              .startRun(text: 'hi', clientMessageId: 'cmid_fail')
              .toList();
          fail('Should have thrown RunStreamException');
        } on RunStreamException catch (e) {
          expect(e.category, ErrorCategory.quotaExhausted);
        }
      },
    );

    test(
      'pre-stream error: 429 BETA_CAPACITY_FULL maps to capacityFull with retryAfter',
      () async {
        final mockClient = MockClient.streaming((request, bodyStream) async {
          final errorJson = jsonEncode({
            'detail': {'code': 'BETA_CAPACITY_FULL', 'retry_after_s': 45},
          });
          return http.StreamedResponse(
            Stream.value(utf8.encode(errorJson)),
            429,
            headers: {'content-type': 'application/json'},
          );
        });

        final client = RunStreamClient(
          baseUrl: 'http://test.karmi.ai',
          client: mockClient,
        );

        try {
          await client
              .startRun(text: 'hi', clientMessageId: 'cmid_fail')
              .toList();
          fail('Should have thrown RunStreamException');
        } on RunStreamException catch (e) {
          expect(e.category, ErrorCategory.capacityFull);
          expect(e.retryAfterSeconds, 45);
          expect(e.retryAfterS, 45);
        }
      },
    );

    test('pre-stream error: 401 triggers onUnauthorized callback', () async {
      bool unauthorizedCalled = false;

      final mockClient = MockClient.streaming((request, bodyStream) async {
        return http.StreamedResponse(
          Stream.value(utf8.encode('{"detail":"Token expired"}')),
          401,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
        onUnauthorized: () => unauthorizedCalled = true,
      );

      try {
        await client.startRun(text: 'hi', clientMessageId: 'c1').toList();
        fail('Should have thrown RunStreamException');
      } on RunStreamException catch (e) {
        expect(e.category, ErrorCategory.unauthorized);
        expect(unauthorizedCalled, isTrue);
      }
    });

    test('pre-stream error: 503 maps to providerUnavailable', () async {
      final mockClient = MockClient.streaming((request, bodyStream) async {
        return http.StreamedResponse(
          Stream.value(utf8.encode('{"detail":"Model service down"}')),
          503,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
      );

      try {
        await client.startRun(text: 'hi', clientMessageId: 'c1').toList();
        fail('Should have thrown');
      } on RunStreamException catch (e) {
        expect(e.category, ErrorCategory.providerUnavailable);
      }
    });

    test(
      'pre-stream error: initial network failure maps to network category',
      () async {
        final mockClient = MockClient.streaming((request, bodyStream) async {
          throw const SocketException('Connection refused');
        });

        final client = RunStreamClient(
          baseUrl: 'http://test.karmi.ai',
          client: mockClient,
        );

        try {
          await client.startRun(text: 'hi', clientMessageId: 'c1').toList();
          fail('Should have thrown RunStreamException');
        } on RunStreamException catch (e) {
          expect(e.category, ErrorCategory.network);
        }
      },
    );

    test(
      'network drop: stream closes before terminal event throws network error',
      () async {
        final mockClient = MockClient.streaming((request, bodyStream) async {
          // Stream sends run.started and delta 1, then abruptly closes
          final responseText =
              'event: run.started\n'
              'data: {"run_id":"r1","conversation_id":"c1","user_message_id":"u1","assistant_message_id":"a1","seq":0}\n\n'
              'id: 1\n'
              'event: message.delta\n'
              'data: {"text":"partial..."}\n\n';

          return http.StreamedResponse(
            Stream.value(utf8.encode(responseText)),
            200,
            headers: {'content-type': 'text/event-stream'},
          );
        });

        final client = RunStreamClient(
          baseUrl: 'http://test.karmi.ai',
          client: mockClient,
        );

        final stream = client.startRun(text: 'hi', clientMessageId: 'c1');
        final receivedEvents = <RunEvent>[];

        try {
          await for (final event in stream) {
            receivedEvents.add(event);
          }
          fail('Should have thrown RunStreamException due to premature close');
        } on RunStreamException catch (e) {
          expect(receivedEvents.length, 2);
          expect(e.category, ErrorCategory.network);
          expect(e.lastSeq, 1);
          expect(client.lastSeq, 1);
        }
      },
    );

    test(
      'network drop: underlying socket error during stream throws network error',
      () async {
        final controller = StreamController<List<int>>();

        final mockClient = MockClient.streaming((request, bodyStream) async {
          return http.StreamedResponse(
            controller.stream,
            200,
            headers: {'content-type': 'text/event-stream'},
          );
        });

        final client = RunStreamClient(
          baseUrl: 'http://test.karmi.ai',
          client: mockClient,
        );

        final stream = client.startRun(text: 'hi', clientMessageId: 'c1');
        final received = <RunEvent>[];

        // Feed initial delta then error
        controller.add(
          utf8.encode(
            'id: 4\n'
            'event: message.delta\n'
            'data: {"text":"hello"}\n\n',
          ),
        );

        // After small delay, inject socket error
        Future.delayed(const Duration(milliseconds: 20), () {
          controller.addError(const SocketException('Broken pipe'));
        });

        try {
          await for (final event in stream) {
            received.add(event);
          }
          fail('Should have thrown RunStreamException');
        } on RunStreamException catch (e) {
          expect(received.length, 1);
          expect(e.category, ErrorCategory.network);
          expect(e.lastSeq, 4);
        } finally {
          await controller.close();
        }
      },
    );

    test('dynamic tokenProvider is called on each request', () async {
      int tokenCalls = 0;
      final mockClient = MockClient.streaming((request, bodyStream) async {
        expect(request.headers['Authorization'], 'Bearer token-$tokenCalls');
        return http.StreamedResponse(
          Stream.value(
            utf8.encode(
              'event: run.finished\ndata: {"finish_reason":"stop"}\n\n',
            ),
          ),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });

      final client = RunStreamClient(
        baseUrl: 'http://test.karmi.ai',
        client: mockClient,
        tokenProvider: () async {
          tokenCalls++;
          return 'token-$tokenCalls';
        },
      );

      await client.startRun(text: 't1', clientMessageId: 'c1').toList();
      expect(tokenCalls, 1);

      await client.startRun(text: 't2', clientMessageId: 'c2').toList();
      expect(tokenCalls, 2);
    });

    test('RunStreamClient.fromApi inherits config from KarmiApi', () async {
      final api = KarmiApi(
        baseUrl: 'http://api.karmi.ai',
        token: 'karmi-api-token',
      );

      final client = RunStreamClient.fromApi(api);
      expect(client.baseUrl, 'http://api.karmi.ai');
      expect(client.token, 'karmi-api-token');
    });
  });
}
