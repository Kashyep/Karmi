import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/stream/sse_parser.dart';

void main() {
  group('SseParser', () {
    test('parses a single standard frame', () async {
      final input = Stream.fromIterable([
        'event: run.started\n'
            'id: 0\n'
            'data: {"run_id":"run_1"}\n\n',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'run.started');
      expect(messages.first.id, '0');
      expect(messages.first.idAsInt, 0);
      expect(messages.first.data, '{"run_id":"run_1"}');
    });

    test('handles frames split across arbitrary chunks', () async {
      final chunks = [
        'eve',
        'nt: message.',
        'delta\nid: 1\n',
        'data: {"text":',
        ' "Hello ',
        'world"}\n\n',
      ];

      final input = Stream.fromIterable(chunks);
      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'message.delta');
      expect(messages.first.id, '1');
      expect(messages.first.idAsInt, 1);
      expect(messages.first.data, '{"text": "Hello world"}');
    });

    test('handles chunk split directly between CR and LF', () async {
      final chunks = [
        'event: message.delta\r',
        '\ndata: {"text":"ok"}\r',
        '\n\r',
        '\n',
      ];

      final input = Stream.fromIterable(chunks);
      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'message.delta');
      expect(messages.first.data, '{"text":"ok"}');
    });

    test('handles extreme 1-character chunks', () async {
      const raw = 'event: test\nid: 7\ndata: payload\n\n';
      final chunks = raw.split('');
      final input = Stream.fromIterable(chunks);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'test');
      expect(messages.first.id, '7');
      expect(messages.first.idAsInt, 7);
      expect(messages.first.data, 'payload');
    });

    test('joins multi-line data with newline', () async {
      final input = Stream.fromIterable([
        'data: line 1\n'
            'data: line 2\n'
            'data: line 3\n\n',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.data, 'line 1\nline 2\nline 3');
    });

    test('handles various line terminators: CRLF, LF, and CR', () async {
      final input = Stream.fromIterable([
        'event: e1\r\ndata: d1\r\n\r\n'
            'event: e2\ndata: d2\n\n'
            'event: e3\rdata: d3\r\r',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 3);
      expect(messages[0].event, 'e1');
      expect(messages[0].data, 'd1');
      expect(messages[1].event, 'e2');
      expect(messages[1].data, 'd2');
      expect(messages[2].event, 'e3');
      expect(messages[2].data, 'd3');
    });

    test('ignores comments and heartbeat-only lines', () async {
      final input = Stream.fromIterable([
        ': heartbeat\n\n'
            ': keepalive\n'
            ':\n'
            'event: message.delta\n'
            ': embedded comment\n'
            'data: {"text":"alive"}\n\n'
            ': final heartbeat\n',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'message.delta');
      expect(messages.first.data, '{"text":"alive"}');
    });

    test('parses real heartbeat event frame', () async {
      final input = Stream.fromIterable([
        'event: heartbeat\n'
            'data: {"at":"2026-10-21T12:00:00Z"}\n\n',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'heartbeat');
      expect(messages.first.data, '{"at":"2026-10-21T12:00:00Z"}');
    });

    test('ignores unknown fields', () async {
      final input = Stream.fromIterable([
        'retry: 3000\n'
            'custom_header: ignore_me\n'
            'event: run.started\n'
            'data: {}\n\n',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'run.started');
      expect(messages.first.data, '{}');
    });

    test(
      'handles terminal event without trailing blank line on stream end',
      () async {
        final input = Stream.fromIterable([
          'event: run.finished\n'
              'data: {"finish_reason":"stop"}',
        ]);

        final messages = await SseParser.parseStrings(input).toList();

        expect(messages.length, 1);
        expect(messages.first.event, 'run.finished');
        expect(messages.first.data, '{"finish_reason":"stop"}');
      },
    );

    test('handles terminal event without trailing newline at all', () async {
      final input = Stream.fromIterable([
        'event: run.finished\r\n'
            'data: {"finish_reason":"length"}',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'run.finished');
      expect(messages.first.data, '{"finish_reason":"length"}');
    });

    test(
      'parses raw byte streams with UTF-8 and Devanagari characters',
      () async {
        final text =
            'event: message.delta\n'
            'id: 2\n'
            'data: {"text":"नमस्ते दुनिया ✨"}\n\n';
        final bytes = utf8.encode(text);

        // Split bytes midway through a multi-byte UTF-8 character
        final mid = bytes.length ~/ 2;
        final byteStream = Stream.fromIterable([
          bytes.sublist(0, mid),
          bytes.sublist(mid),
        ]);

        final messages = await SseParser.parseBytes(byteStream).toList();

        expect(messages.length, 1);
        expect(messages.first.event, 'message.delta');
        expect(messages.first.id, '2');
        expect(messages.first.data, '{"text":"नमस्ते दुनिया ✨"}');
      },
    );

    test('works as StreamTransformer with stream.transform()', () async {
      final input = Stream.fromIterable([
        'event: run.started\n'
            'data: {"seq":0}\n\n',
      ]);

      final messages = await input.transform(const SseParser()).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'run.started');
      expect(messages.first.data, '{"seq":0}');
    });
  });
}
