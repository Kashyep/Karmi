// R1 streaming perf: N message.delta events through the real ChatScreen.
// Host-VM widget-test proxy (NOT device frame timings).
//
// Same file runs on HEAD and on the baseline tree (dcf4f75). The two trees use
// different send paths, so the fake backend registers both routes:
//   - HEAD streaming path: POST /v1/chat/stream returns one SSE body with
//     N message.delta events (a real multi-delta stream, parsed by the client).
//   - Baseline legacy path: POST /v1/messages is non-streaming; it returns the
//     same N tokens as one whole JSON reply (no per-delta stream exists there).
// Only the route the tree actually calls is hit; the numbers are labelled by
// tree in docs/release1/perf/AFTER.md.
//
// Run: cd mobile && TZ=Asia/Kolkata flutter test test/perf/stream_perf_test.dart --reporter expanded
// Emits lines prefixed `PERF ` for capture into docs/release1/perf/*.md.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../support/fake_backend.dart';
import '../support/harness.dart';

const int _deltaCount = 200;

double _median(List<double> xs) {
  final s = [...xs]..sort();
  return s[s.length ~/ 2];
}

double _p95(List<double> xs) {
  final s = [...xs]..sort();
  return s[math.min(s.length - 1, (s.length * 0.95).ceil() - 1)];
}

// ignore: avoid_print
void _perf(String line) => print('PERF $line');

List<String> get _tokens => [
  for (var i = 1; i <= _deltaCount; i++) 'tok$i ',
];

FakeBackend _streamingBackend() {
  final tokens = _tokens;
  final sse = StringBuffer()
    ..write('event: run.started\n')
    ..write(
      'data: {"run_id":"run-1","conversation_id":"conv-1",'
      '"user_message_id":"msg-u-1","assistant_message_id":"msg-a-1","seq":0}\n\n',
    );
  for (var i = 0; i < tokens.length; i++) {
    sse
      ..write('id: ${i + 1}\n')
      ..write('event: message.delta\n')
      ..write('data: {"text":"${tokens[i]}"}\n\n');
  }
  sse
    ..write('event: run.finished\n')
    ..write('data: {"finish_reason":"stop","outcome":"success"}\n\n');
  final body = sse.toString();
  final wholeReply = tokens.join();
  return FakeBackend.healthy()
    ..on(
      'POST',
      '/v1/chat/stream',
      (_) => http.Response(
        body,
        200,
        headers: {'content-type': 'text/event-stream'},
      ),
    )
    ..on(
      'POST',
      '/v1/messages',
      (_) => jsonResponse(messageJson('ACCEPT', response: wholeReply)),
    );
}

const _rebuildNames = ['ChatScreen', 'MessageBubble', '_UserRow', 'Composer'];

void main() {
  testWidgets(
    'PERF streaming: rebuilds and frame build time per $_deltaCount deltas (host VM)',
    (tester) async {
      final lines = <String>[];
      final originalPrint = debugPrint;
      final savedFlag = debugPrintRebuildDirtyWidgets;
      debugPrint = (String? message, {int? wrapWidth}) {
        if (message != null) lines.add(message);
      };
      debugPrintRebuildDirtyWidgets = true;
      try {
        await pumpApp(tester, backend: _streamingBackend());
        lines.clear();

        await tester.enterText(find.byType(TextField), 'Stream the plan');
        await tester.pump();
        await tester.tap(find.byTooltip('Send message'));

        final frameMs = <double>[];
        for (var i = 0; i < 200; i++) {
          final sw = Stopwatch()..start();
          await tester.pump(const Duration(milliseconds: 16));
          sw.stop();
          frameMs.add(sw.elapsedMicroseconds / 1000);
          await tester.runAsync(() => Future<void>.delayed(Duration.zero));
        }

        final rebuilds = lines
            .where(
              (l) =>
                  l.startsWith('Rebuilding') && _rebuildNames.any(l.contains),
            )
            .length;
        _perf(
          'streaming_rebuilds deltas=$_deltaCount total=$rebuilds '
          'per_delta=${(rebuilds / _deltaCount).toStringAsFixed(3)} '
          'note=filtered debugPrintRebuildDirtyWidgets lines naming '
          '${_rebuildNames.join('/')}',
        );
        _perf(
          'streaming_frame_build_ms median=${_median(frameMs).toStringAsFixed(2)} '
          'p95=${_p95(frameMs).toStringAsFixed(2)} frames=${frameMs.length} '
          'note=pump(16ms) wall time per frame, host VM, no raster/GPU',
        );
      } finally {
        debugPrint = originalPrint;
        debugPrintRebuildDirtyWidgets = savedFlag;
      }
    },
  );
}
