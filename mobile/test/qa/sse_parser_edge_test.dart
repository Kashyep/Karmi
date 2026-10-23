import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/stream/sse_parser.dart';

void main() {
  group('SseParser edge cases', () {
    test(
      'split frames across chunk boundaries: 1-char chunks and mid-token splits',
      () async {
        const raw =
            'event: run.started\n'
            'id: 1\n'
            'data: {"run_id":"r_1","seq":1}\n\n'
            'event: message.delta\n'
            'id: 2\n'
            'data: {"text":"hello world"}\n\n';

        // Feed every character as its own separate chunk
        final charChunks = raw.split('');
        final messages = await SseParser.parseStrings(
          Stream.fromIterable(charChunks),
        ).toList();

        expect(messages.length, 2);
        expect(messages[0].event, 'run.started');
        expect(messages[0].id, '1');
        expect(messages[0].idAsInt, 1);
        expect(messages[0].data, '{"run_id":"r_1","seq":1}');

        expect(messages[1].event, 'message.delta');
        expect(messages[1].id, '2');
        expect(messages[1].idAsInt, 2);
        expect(messages[1].data, '{"text":"hello world"}');
      },
    );

    test(
      'heartbeat comments (: heartbeat) ignored for seq and produce no message',
      () async {
        final input = Stream.fromIterable([
          'event: message.delta\n'
              'id: 1\n'
              'data: {"text":"part 1"}\n\n',
          ': heartbeat\n\n',
          ': keepalive ping\n',
          ':\n\n',
          'event: message.delta\n'
              'id: 2\n'
              'data: {"text":"part 2"}\n\n',
        ]);

        final messages = await SseParser.parseStrings(input).toList();

        expect(messages.length, 2);
        expect(messages[0].event, 'message.delta');
        expect(messages[0].id, '1');
        expect(messages[0].idAsInt, 1);
        expect(messages[0].data, '{"text":"part 1"}');

        expect(messages[1].event, 'message.delta');
        expect(messages[1].id, '2');
        expect(messages[1].idAsInt, 2);
        expect(messages[1].data, '{"text":"part 2"}');
      },
    );

    test(
      'heartbeat event frame has null id and is ignored for sequence tracking',
      () async {
        final input = Stream.fromIterable([
          'event: heartbeat\n'
              'data: {"at":"2026-10-21T10:00:00Z"}\n\n',
        ]);

        final messages = await SseParser.parseStrings(input).toList();

        expect(messages.length, 1);
        final hb = messages.first;
        expect(hb.event, 'heartbeat');
        expect(hb.id, isNull);
        expect(hb.idAsInt, isNull);
        expect(hb.data, '{"at":"2026-10-21T10:00:00Z"}');
      },
    );

    test('multi-line data joined with \\n across chunk boundaries', () async {
      final chunks = [
        'event: message.delta\n',
        'id: 3\n',
        'data: {\n',
        'data:   "line": 1,\n',
        'data:   "line": 2\n',
        'data: }\n\n',
      ];

      final messages = await SseParser.parseStrings(
        Stream.fromIterable(chunks),
      ).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'message.delta');
      expect(messages.first.id, '3');
      expect(messages.first.data, '{\n  "line": 1,\n  "line": 2\n}');
    });

    test('CRLF and LF handled correctly within and between frames', () async {
      final input = Stream.fromIterable([
        'event: e1\r\nid: 1\r\ndata: d1\r\n\r\n',
        'event: e2\nid: 2\ndata: d2\n\n',
        'event: e3\r\nid: 3\ndata: d3_line1\ndata: d3_line2\r\n\r\n',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 3);
      expect(messages[0].event, 'e1');
      expect(messages[0].id, '1');
      expect(messages[0].data, 'd1');

      expect(messages[1].event, 'e2');
      expect(messages[1].id, '2');
      expect(messages[1].data, 'd2');

      expect(messages[2].event, 'e3');
      expect(messages[2].id, '3');
      expect(messages[2].data, 'd3_line1\nd3_line2');
    });

    test(
      'trailing incomplete field or comment without colon is not emitted',
      () async {
        final input = Stream.fromIterable([
          'event: message.delta\n'
              'id: 1\n'
              'data: {"text":"complete"}\n\n'
              'incomplete_chunk_without_colon',
        ]);

        final messages = await SseParser.parseStrings(input).toList();

        expect(messages.length, 1);
        expect(messages.first.event, 'message.delta');
        expect(messages.first.data, '{"text":"complete"}');
      },
    );

    test('trailing incomplete comment line is not emitted', () async {
      final input = Stream.fromIterable([
        'event: run.started\n'
            'id: 0\n'
            'data: {"seq":0}\n\n'
            ': trailing comment without newline',
      ]);

      final messages = await SseParser.parseStrings(input).toList();

      expect(messages.length, 1);
      expect(messages.first.event, 'run.started');
      expect(messages.first.data, '{"seq":0}');
    });
  });
}
